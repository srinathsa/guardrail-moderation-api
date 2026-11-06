"""SQLAlchemy ORM models."""
import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.db.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    content_type = Column(String(10), nullable=False)  # "text" | "image"
    detected_language = Column(String(20), nullable=True)
    input_preview = Column(Text, nullable=False)

    scores_json = Column(Text, nullable=False)  # JSON-encoded dict of category -> score
    decision = Column(String(10), nullable=False, index=True)  # allow|flag|block
    reasons_json = Column(Text, nullable=False)  # JSON-encoded list[str]
    model_used = Column(String(100), nullable=False)
    processing_time_ms = Column(Float, nullable=False)

    # --- Human review / human-in-the-loop fields ---
    review_status = Column(String(20), nullable=False, default="pending", index=True)  # pending|approved|rejected
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)

    # --- convenience (de)serialization helpers ---
    @property
    def scores(self) -> dict:
        return json.loads(self.scores_json)

    @scores.setter
    def scores(self, value: dict):
        self.scores_json = json.dumps(value)

    @property
    def reasons(self) -> list:
        return json.loads(self.reasons_json)

    @reasons.setter
    def reasons(self, value: list):
        self.reasons_json = json.dumps(value)


class User(Base):
    """Human dashboard users (admin / moderator / client), JWT-authenticated."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="client")  # admin|moderator|client
    created_at = Column(DateTime, default=datetime.utcnow)


class BlocklistTerm(Base):
    """Admin-managed custom banned words/phrases, checked against every text submission."""
    __tablename__ = "blocklist_terms"

    id = Column(Integer, primary_key=True, index=True)
    term = Column(String(200), nullable=False, unique=True)
    added_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Post(Base):
    """
    Public social-feed content (posts and comments). Anyone can browse the
    feed without logging in, but posting/commenting requires a real account
    (author_name is always the authenticated username, not client-supplied
    text — see routes_feed.py). Every post and comment is moderated at
    submission time and linked to its audit log via audit_log_id;
    visibility in the feed is derived at read time from that audit log's
    decision + review_status (see crud.get_feed).
    """
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(10), nullable=False)  # "post" | "comment"
    parent_id = Column(Integer, ForeignKey("posts.id"), nullable=True, index=True)
    author_name = Column(String(100), nullable=False)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    text_content = Column(Text, nullable=True)
    media_filename = Column(String(255), nullable=True)
    media_type = Column(String(10), nullable=True)  # "image" | "video"
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    audit_log_id = Column(Integer, ForeignKey("audit_logs.id"), nullable=True)
