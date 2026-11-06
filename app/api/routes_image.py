"""POST /moderate/image"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import crud
from app.db.database import get_db
from app.guardrail.rules import decide
from app.models.image_moderation import moderate_image
from app.schemas import ModerationResult

router = APIRouter(tags=["moderation"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/moderate/image", response_model=ModerationResult)
async def moderate_image_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type '{file.content_type}'. Allowed: JPEG, PNG, WEBP.",
        )

    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 10MB limit")

    scores, model_used, elapsed_ms = moderate_image(image_bytes)
    # Only "harm" categories should be evaluated against the guardrail
    # thresholds. `normal` is a safety/benign signal, not a harm category,
    # so it must be excluded from block/flag decisioning (a high "normal"
    # score means the image is SAFE, not that it should be blocked).
    harm_scores = {k: v for k, v in scores.items() if k != "normal"}
    decision, reasons = decide(harm_scores)

    preview = f"[image] filename={file.filename} content_type={file.content_type} size={len(image_bytes)}B"
    entry = crud.create_audit_log(
        db,
        content_type="image",
        detected_language=None,
        input_preview=preview,
        scores=scores,
        decision=decision,
        reasons=reasons,
        model_used=model_used,
        processing_time_ms=elapsed_ms,
    )

    return ModerationResult(
        id=entry.id,
        content_type="image",
        detected_language=None,
        decision=decision,
        reasons=reasons,
        scores=scores,
        model_used=model_used,
        processing_time_ms=elapsed_ms,
        review_status=entry.review_status,
    )
