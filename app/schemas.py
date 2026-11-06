"""Pydantic request/response schemas."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TextModerationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000, description="Text to moderate")


class ModerationResult(BaseModel):
    id: int
    content_type: str  # "text" | "image"
    detected_language: Optional[str] = None
    decision: str  # allow | flag | block
    reasons: List[str]
    scores: Dict[str, float]
    model_used: str
    processing_time_ms: float
    review_status: str = "pending"


class AuditLogOut(BaseModel):
    id: int
    timestamp: datetime
    content_type: str
    detected_language: Optional[str]
    input_preview: str
    scores: Dict[str, float]
    decision: str
    reasons: List[str]
    model_used: str
    processing_time_ms: float
    review_status: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    total: int
    items: List[AuditLogOut]


class ReviewUpdateRequest(BaseModel):
    review_status: str = Field(..., description="approved | rejected")
    reviewed_by: str = Field(..., min_length=1, max_length=100)
    review_notes: Optional[str] = Field(default=None, max_length=2000)


# --- Auth ---
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)
    role: str = Field(..., description="admin | moderator | client")


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class MeResponse(BaseModel):
    username: str
    role: str


# --- Blocklist ---
class BlocklistTermRequest(BaseModel):
    term: str = Field(..., min_length=1, max_length=200)


class BlocklistTermOut(BaseModel):
    id: int
    term: str
    added_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Analytics ---
class DayCount(BaseModel):
    date: str
    allow: int = 0
    flag: int = 0
    block: int = 0


class ModeratorStat(BaseModel):
    reviewed_by: str
    reviews: int
    approved: int
    rejected: int


class AnalyticsSummary(BaseModel):
    totals: Dict[str, int]
    by_day: List[DayCount]
    category_averages: Dict[str, float]
    review_stats: Dict[str, int]
    false_positive_rate: Optional[float]
    moderator_stats: List[ModeratorStat]


# --- Public social feed ---
class CommentOut(BaseModel):
    id: int
    author_name: str
    text_content: Optional[str]
    created_at: datetime


class PostOut(BaseModel):
    id: int
    author_name: str
    text_content: Optional[str]
    media_url: Optional[str]
    media_type: Optional[str]  # "image" | "video"
    created_at: datetime
    comments: List[CommentOut] = []


class FeedResponse(BaseModel):
    items: List[PostOut]


class CreatePostStatusOut(BaseModel):
    id: int
    decision: str
    review_status: str
    visible: bool
    reasons: List[str]


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)
