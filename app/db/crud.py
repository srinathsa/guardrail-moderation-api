"""Database access helpers (CRUD) for audit logs, users, and the blocklist."""
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models import AuditLog, BlocklistTerm, Post, User


def create_audit_log(
    db: Session,
    *,
    content_type: str,
    detected_language: Optional[str],
    input_preview: str,
    scores: Dict[str, float],
    decision: str,
    reasons: List[str],
    model_used: str,
    processing_time_ms: float,
) -> AuditLog:
    entry = AuditLog(
        content_type=content_type,
        detected_language=detected_language,
        input_preview=input_preview,
        decision=decision,
        model_used=model_used,
        processing_time_ms=processing_time_ms,
        review_status="pending",
    )
    entry.scores = scores
    entry.reasons = reasons
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_audit_logs(
    db: Session,
    *,
    review_status: Optional[str] = None,
    decision: Optional[str] = None,
    content_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[int, List[AuditLog]]:
    query = db.query(AuditLog)
    if review_status:
        query = query.filter(AuditLog.review_status == review_status)
    if decision:
        query = query.filter(AuditLog.decision == decision)
    if content_type:
        query = query.filter(AuditLog.content_type == content_type)

    total = query.count()
    items = (
        query.order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, items


def get_audit_log(db: Session, log_id: int) -> Optional[AuditLog]:
    return db.query(AuditLog).filter(AuditLog.id == log_id).first()


def update_review(
    db: Session,
    log_id: int,
    *,
    review_status: str,
    reviewed_by: str,
    review_notes: Optional[str],
) -> Optional[AuditLog]:
    entry = get_audit_log(db, log_id)
    if entry is None:
        return None
    entry.review_status = review_status
    entry.reviewed_by = reviewed_by
    entry.reviewed_at = datetime.utcnow()
    entry.review_notes = review_notes
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def any_users_exist(db: Session) -> bool:
    return db.query(User).first() is not None


def create_user(db: Session, *, username: str, password_hash: str, role: str) -> User:
    user = User(username=username, password_hash=password_hash, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> List[User]:
    return db.query(User).order_by(User.created_at.asc()).all()


def delete_user(db: Session, user_id: int) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Blocklist
# ---------------------------------------------------------------------------
def list_blocklist(db: Session) -> List[BlocklistTerm]:
    return db.query(BlocklistTerm).order_by(BlocklistTerm.created_at.desc()).all()


def add_blocklist_term(db: Session, *, term: str, added_by: str) -> BlocklistTerm:
    existing = db.query(BlocklistTerm).filter(BlocklistTerm.term == term.lower()).first()
    if existing:
        return existing
    entry = BlocklistTerm(term=term.lower(), added_by=added_by)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def delete_blocklist_term(db: Session, term_id: int) -> bool:
    entry = db.query(BlocklistTerm).filter(BlocklistTerm.id == term_id).first()
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    return True


def check_blocklist(db: Session, text: str) -> List[str]:
    """Returns the list of blocklist terms found in `text` (word-boundary, case-insensitive)."""
    terms = db.query(BlocklistTerm).all()
    lowered = text.lower()
    hits = []
    for entry in terms:
        pattern = r"\b" + re.escape(entry.term) + r"\b"
        if re.search(pattern, lowered):
            hits.append(entry.term)
    return hits


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
def get_analytics_summary(db: Session, *, days_back: int = 30) -> Dict:
    logs: List[AuditLog] = db.query(AuditLog).all()

    totals = {"total": len(logs), "allow": 0, "flag": 0, "block": 0}
    by_day: Dict[str, Dict[str, int]] = defaultdict(lambda: {"allow": 0, "flag": 0, "block": 0})
    category_sums: Dict[str, float] = defaultdict(float)
    category_counts: Dict[str, int] = defaultdict(int)
    review_stats = {"pending": 0, "approved": 0, "rejected": 0}
    moderator_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"reviews": 0, "approved": 0, "rejected": 0})

    flagged_or_blocked = 0
    approved_count = 0

    for log in logs:
        totals[log.decision] = totals.get(log.decision, 0) + 1
        day_key = log.timestamp.strftime("%Y-%m-%d") if log.timestamp else "unknown"
        by_day[day_key][log.decision] = by_day[day_key].get(log.decision, 0) + 1

        if log.content_type == "text":
            for cat, val in log.scores.items():
                category_sums[cat] += val
                category_counts[cat] += 1

        review_stats[log.review_status] = review_stats.get(log.review_status, 0) + 1

        if log.decision in ("flag", "block"):
            flagged_or_blocked += 1
            if log.review_status == "approved":
                approved_count += 1

        if log.reviewed_by:
            moderator_stats[log.reviewed_by]["reviews"] += 1
            if log.review_status == "approved":
                moderator_stats[log.reviewed_by]["approved"] += 1
            elif log.review_status == "rejected":
                moderator_stats[log.reviewed_by]["rejected"] += 1

    category_averages = {
        cat: round(category_sums[cat] / category_counts[cat], 4)
        for cat in category_sums if category_counts[cat] > 0
    }

    false_positive_rate = (
        round(approved_count / flagged_or_blocked, 4) if flagged_or_blocked > 0 else None
    )

    by_day_list = [
        {"date": day, **counts} for day, counts in sorted(by_day.items())
    ]

    moderator_stats_list = [
        {"reviewed_by": name, **stats} for name, stats in moderator_stats.items()
    ]

    return {
        "totals": totals,
        "by_day": by_day_list,
        "category_averages": category_averages,
        "review_stats": review_stats,
        "false_positive_rate": false_positive_rate,
        "moderator_stats": moderator_stats_list,
    }


# ---------------------------------------------------------------------------
# Public social feed (posts + comments)
# ---------------------------------------------------------------------------
def create_post(
    db: Session,
    *,
    kind: str,
    parent_id: Optional[int],
    author_name: str,
    author_user_id: Optional[int],
    text_content: Optional[str],
    media_filename: Optional[str],
    media_type: Optional[str],
    audit_log_id: Optional[int],
) -> Post:
    post = Post(
        kind=kind,
        parent_id=parent_id,
        author_name=author_name,
        author_user_id=author_user_id,
        text_content=text_content,
        media_filename=media_filename,
        media_type=media_type,
        audit_log_id=audit_log_id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def get_post(db: Session, post_id: int) -> Optional[Post]:
    return db.query(Post).filter(Post.id == post_id).first()


def _is_visible(db: Session, post: Post) -> bool:
    """A post/comment is publicly visible if it was auto-allowed, or if a
    human moderator later approved a flagged/blocked decision."""
    if not post.audit_log_id:
        return True
    log = db.query(AuditLog).filter(AuditLog.id == post.audit_log_id).first()
    if not log:
        return True
    if log.decision == "allow":
        return True
    return log.review_status == "approved"


def get_feed(db: Session, *, limit: int = 30) -> List[Tuple[Post, List[Post]]]:
    """Returns [(post, [visible_comments]), ...] newest post first, visible only."""
    posts = (
        db.query(Post)
        .filter(Post.kind == "post")
        .order_by(Post.created_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for post in posts:
        if not _is_visible(db, post):
            continue
        comments = (
            db.query(Post)
            .filter(Post.kind == "comment", Post.parent_id == post.id)
            .order_by(Post.created_at.asc())
            .all()
        )
        visible_comments = [c for c in comments if _is_visible(db, c)]
        result.append((post, visible_comments))
    return result


def get_post_status(db: Session, post_id: int) -> Optional[Tuple[Post, Optional[AuditLog]]]:
    post = get_post(db, post_id)
    if not post:
        return None
    log = db.query(AuditLog).filter(AuditLog.id == post.audit_log_id).first() if post.audit_log_id else None
    return post, log
