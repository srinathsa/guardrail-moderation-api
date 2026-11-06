"""
POST /feed/posts, POST /feed/posts/{id}/comments, GET /feed/posts,
GET /feed/posts/{id}/status — the social feed.

Posting/commenting requires a logged-in account (any role — regular users
self-register via POST /auth/register, exactly like signing up for a real
social app). The author is always taken from the authenticated JWT, never
from client-supplied text, so people can't impersonate someone else. Browsing
the feed itself (GET) does not require login, same as viewing public posts
on a real platform before you sign in.

Every submission is run through the full moderation pipeline before it's
stored. Images are scored by the NSFW model; video content isn't deeply
analyzed (no video/frame-extraction pipeline in this project), so any video
is always at least "flag"'d for a human to review — a deliberately safe
default rather than silently trusting unscored video.
"""
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.db import crud
from app.db.database import get_db
from app.guardrail.rules import decide
from app.models.image_moderation import moderate_image
from app.models.pii_detect import detect_pii
from app.models.text_moderation import moderate_text
from app.schemas import CommentOut, CreatePostStatusOut, FeedResponse, PostOut

router = APIRouter(prefix="/feed", tags=["feed"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
_DECISION_RANK = {"allow": 0, "flag": 1, "block": 2}

os.makedirs(settings.MEDIA_DIR, exist_ok=True)


def _moderate_and_log(
    db: Session,
    *,
    content_type_label: str,
    text: Optional[str],
    image_bytes: Optional[bytes],
    is_video: bool,
):
    """Runs the full pipeline on whatever content is present (text and/or
    image and/or video) and stores one combined audit log entry."""
    scores = {}
    reasons: List[str] = []
    decisions: List[str] = []
    model_parts: List[str] = []
    lang = None

    if text:
        text_scores, detected_lang, text_model, _elapsed = moderate_text(text)
        lang = detected_lang
        text_decision, text_reasons = decide(text_scores)

        blocklist_hits = crud.check_blocklist(db, text)
        if blocklist_hits:
            text_decision = "block"
            text_reasons = text_reasons + [f"blocklist match: '{t}'" for t in blocklist_hits]

        pii_types = detect_pii(text)
        if pii_types:
            text_reasons = text_reasons + [f"PII detected: {t}" for t in pii_types]
            if text_decision == "allow":
                text_decision = "flag"

        scores.update({f"text_{k}": v for k, v in text_scores.items()})
        reasons += [f"text: {r}" for r in text_reasons]
        decisions.append(text_decision)
        model_parts.append(text_model)

    if image_bytes and not is_video:
        image_scores, image_model, _elapsed = moderate_image(image_bytes)
        harm_scores = {k: v for k, v in image_scores.items() if k != "normal"}
        image_decision, image_reasons = decide(harm_scores)
        scores.update({f"image_{k}": v for k, v in image_scores.items()})
        reasons += [f"image: {r}" for r in image_reasons]
        decisions.append(image_decision)
        model_parts.append(image_model)

    if is_video:
        # No video-content analysis pipeline in this project — always route
        # to human review rather than silently auto-allowing unscored video.
        decisions.append("flag")
        reasons.append("video: requires manual review (automated video content analysis not implemented)")
        model_parts.append("video-unscored")

    final_decision = max(decisions, key=lambda d: _DECISION_RANK[d]) if decisions else "allow"
    if not reasons:
        reasons = ["no content submitted"]

    preview_parts = []
    if text:
        preview_parts.append(text[: settings.INPUT_PREVIEW_CHARS])
    if image_bytes:
        preview_parts.append("[video attached]" if is_video else "[image attached]")

    return crud.create_audit_log(
        db,
        content_type=content_type_label,
        detected_language=lang,
        input_preview=" | ".join(preview_parts),
        scores=scores,
        decision=final_decision,
        reasons=reasons,
        model_used="+".join(model_parts) if model_parts else "n/a",
        processing_time_ms=0.0,
    )


def _save_media(data: bytes, content_type: str, is_video: bool) -> str:
    ext_map = {
        "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
        "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov",
    }
    ext = ext_map.get(content_type, "bin")
    filename = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(settings.MEDIA_DIR, filename), "wb") as f:
        f.write(data)
    return filename


@router.post("/posts", response_model=CreatePostStatusOut)
async def create_post(
    caption: str = Form(default=""),
    media: Optional[UploadFile] = File(default=None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    caption = (caption or "").strip()

    media_bytes = None
    media_filename = None
    media_type = None
    is_video = False

    if media is not None and media.filename:
        if media.content_type in ALLOWED_IMAGE_TYPES:
            media_type = "image"
            max_bytes = MAX_IMAGE_BYTES
        elif media.content_type in ALLOWED_VIDEO_TYPES:
            media_type = "video"
            is_video = True
            max_bytes = MAX_VIDEO_BYTES
        else:
            raise HTTPException(415, "Unsupported media type. Allowed: JPEG/PNG/WEBP images or MP4/WEBM/MOV video.")

        media_bytes = await media.read()
        if len(media_bytes) > max_bytes:
            raise HTTPException(413, f"File exceeds {max_bytes // (1024*1024)}MB limit")

    if not caption and not media_bytes:
        raise HTTPException(400, "Post must include a caption, image, or video")

    entry = _moderate_and_log(db, content_type_label="post", text=caption or None, image_bytes=media_bytes, is_video=is_video)

    if media_bytes:
        media_filename = _save_media(media_bytes, media.content_type, is_video)

    user_record = crud.get_user_by_username(db, user.username)
    post = crud.create_post(
        db,
        kind="post",
        parent_id=None,
        author_name=user.username,
        author_user_id=user_record.id if user_record else None,
        text_content=caption or None,
        media_filename=media_filename,
        media_type=media_type,
        audit_log_id=entry.id,
    )

    return CreatePostStatusOut(
        id=post.id,
        decision=entry.decision,
        review_status=entry.review_status,
        visible=(entry.decision == "allow"),
        reasons=entry.reasons,
    )


@router.post("/posts/{post_id}/comments", response_model=CreatePostStatusOut)
async def create_comment(
    post_id: int,
    text: str = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    parent = crud.get_post(db, post_id)
    if not parent or parent.kind != "post":
        raise HTTPException(404, "Post not found")

    text = (text or "").strip()
    if not text:
        raise HTTPException(400, "Comment text is required")

    entry = _moderate_and_log(db, content_type_label="comment", text=text, image_bytes=None, is_video=False)

    user_record = crud.get_user_by_username(db, user.username)
    comment = crud.create_post(
        db,
        kind="comment",
        parent_id=post_id,
        author_name=user.username,
        author_user_id=user_record.id if user_record else None,
        text_content=text,
        media_filename=None,
        media_type=None,
        audit_log_id=entry.id,
    )

    return CreatePostStatusOut(
        id=comment.id,
        decision=entry.decision,
        review_status=entry.review_status,
        visible=(entry.decision == "allow"),
        reasons=entry.reasons,
    )


@router.get("/posts", response_model=FeedResponse)
async def list_feed(limit: int = 30, db: Session = Depends(get_db)):
    """Browsing the feed doesn't require login, same as viewing public posts
    on a real platform before signing in — only posting/commenting does."""
    pairs = crud.get_feed(db, limit=limit)
    items = [
        PostOut(
            id=post.id,
            author_name=post.author_name,
            text_content=post.text_content,
            media_url=f"/media/{post.media_filename}" if post.media_filename else None,
            media_type=post.media_type,
            created_at=post.created_at,
            comments=[
                CommentOut(id=c.id, author_name=c.author_name, text_content=c.text_content, created_at=c.created_at)
                for c in comments
            ],
        )
        for post, comments in pairs
    ]
    return FeedResponse(items=items)


@router.get("/posts/{post_id}/status", response_model=CreatePostStatusOut)
async def post_status(post_id: int, db: Session = Depends(get_db)):
    result = crud.get_post_status(db, post_id)
    if not result:
        raise HTTPException(404, "Post not found")
    post, log = result
    if not log:
        return CreatePostStatusOut(id=post.id, decision="allow", review_status="approved", visible=True, reasons=[])
    visible = log.decision == "allow" or log.review_status == "approved"
    return CreatePostStatusOut(
        id=post.id, decision=log.decision, review_status=log.review_status, visible=visible, reasons=log.reasons
    )
