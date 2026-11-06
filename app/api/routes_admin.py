"""
GET /audit/logs, PATCH /audit/logs/{id}/review — human review dashboard API.
GET/POST/DELETE /admin/blocklist — admin-managed custom banned terms.

All routes here require a logged-in dashboard user (JWT), not the service
x-api-key: audit review is a human/moderator action, not a service call.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_roles
from app.db import crud
from app.db.database import get_db
from app.schemas import (
    AuditLogListResponse,
    AuditLogOut,
    BlocklistTermOut,
    BlocklistTermRequest,
    ReviewUpdateRequest,
)

router = APIRouter(tags=["audit"])

VALID_REVIEW_STATUSES = {"pending", "approved", "rejected"}
VALID_DECISIONS = {"allow", "flag", "block"}


def _to_out(entry) -> AuditLogOut:
    return AuditLogOut(
        id=entry.id,
        timestamp=entry.timestamp,
        content_type=entry.content_type,
        detected_language=entry.detected_language,
        input_preview=entry.input_preview,
        scores=entry.scores,
        decision=entry.decision,
        reasons=entry.reasons,
        model_used=entry.model_used,
        processing_time_ms=entry.processing_time_ms,
        review_status=entry.review_status,
        reviewed_by=entry.reviewed_by,
        reviewed_at=entry.reviewed_at,
        review_notes=entry.review_notes,
    )


@router.get("/audit/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    review_status: Optional[str] = Query(default=None),
    decision: Optional[str] = Query(default=None),
    content_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin", "moderator")),
):
    if review_status and review_status not in VALID_REVIEW_STATUSES:
        raise HTTPException(400, f"review_status must be one of {sorted(VALID_REVIEW_STATUSES)}")
    if decision and decision not in VALID_DECISIONS:
        raise HTTPException(400, f"decision must be one of {sorted(VALID_DECISIONS)}")

    total, items = crud.get_audit_logs(
        db,
        review_status=review_status,
        decision=decision,
        content_type=content_type,
        limit=limit,
        offset=offset,
    )
    return AuditLogListResponse(total=total, items=[_to_out(i) for i in items])


@router.patch("/audit/logs/{log_id}/review", response_model=AuditLogOut)
async def review_audit_log(
    log_id: int,
    payload: ReviewUpdateRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("admin", "moderator")),
):
    if payload.review_status not in {"approved", "rejected"}:
        raise HTTPException(400, "review_status must be 'approved' or 'rejected'")

    entry = crud.update_review(
        db,
        log_id,
        review_status=payload.review_status,
        reviewed_by=payload.reviewed_by or user.username,
        review_notes=payload.review_notes,
    )
    if entry is None:
        raise HTTPException(404, f"Audit log {log_id} not found")
    return _to_out(entry)


# ---------------------------------------------------------------------------
# Blocklist management
# ---------------------------------------------------------------------------
@router.get("/admin/blocklist", response_model=List[BlocklistTermOut])
async def get_blocklist(
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin", "moderator")),
):
    return crud.list_blocklist(db)


@router.post("/admin/blocklist", response_model=BlocklistTermOut)
async def add_blocklist_term(
    payload: BlocklistTermRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("admin")),
):
    return crud.add_blocklist_term(db, term=payload.term.strip(), added_by=user.username)


@router.delete("/admin/blocklist/{term_id}")
async def delete_blocklist_term(
    term_id: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    ok = crud.delete_blocklist_term(db, term_id)
    if not ok:
        raise HTTPException(404, "Blocklist term not found")
    return {"deleted": True, "id": term_id}
