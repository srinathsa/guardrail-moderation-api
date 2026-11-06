"""GET /analytics/summary — trends, category breakdowns, false-positive rate."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_roles
from app.db import crud
from app.db.database import get_db
from app.schemas import AnalyticsSummary

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin", "moderator")),
):
    data = crud.get_analytics_summary(db)
    return AnalyticsSummary(**data)
