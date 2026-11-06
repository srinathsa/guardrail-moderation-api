"""POST /moderate/text"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.config import settings
from app.db import crud
from app.db.database import get_db
from app.guardrail.rules import decide
from app.models.pii_detect import detect_pii
from app.models.text_moderation import moderate_text
from app.schemas import ModerationResult, TextModerationRequest

router = APIRouter(tags=["moderation"])


@router.post("/moderate/text", response_model=ModerationResult)
async def moderate_text_endpoint(
    payload: TextModerationRequest,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    scores, lang, model_used, elapsed_ms = moderate_text(payload.text)
    decision, reasons = decide(scores)

    # --- Custom admin blocklist: any hit forces a block, regardless of model scores ---
    blocklist_hits = crud.check_blocklist(db, payload.text)
    if blocklist_hits:
        decision = "block"
        reasons = reasons + [f"blocklist match: '{term}'" for term in blocklist_hits]

    # --- PII detection: flags for human review (never auto-escalates past "flag") ---
    pii_types = detect_pii(payload.text)
    if pii_types:
        reasons = reasons + [f"PII detected: {t}" for t in pii_types]
        if decision == "allow":
            decision = "flag"

    preview = payload.text[: settings.INPUT_PREVIEW_CHARS]
    entry = crud.create_audit_log(
        db,
        content_type="text",
        detected_language=lang,
        input_preview=preview,
        scores=scores,
        decision=decision,
        reasons=reasons,
        model_used=model_used,
        processing_time_ms=elapsed_ms,
    )

    return ModerationResult(
        id=entry.id,
        content_type="text",
        detected_language=lang,
        decision=decision,
        reasons=reasons,
        scores=scores,
        model_used=model_used,
        processing_time_ms=elapsed_ms,
        review_status=entry.review_status,
    )
