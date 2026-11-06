"""
Video moderation: extracts the first frame of an uploaded video and runs it
through the existing image NSFW classifier, so a video gets a real score
whenever possible.

Real path: OpenCV (`opencv-python-headless`) reads the video's first frame,
encodes it as JPEG, and hands it to `image_moderation.moderate_image`.

Fallback path (no OpenCV installed, or frame extraction fails for any
reason — corrupt file, unsupported codec, etc.): returns a neutral score
that sits exactly at the default flag threshold, so the video is
automatically held for human review rather than silently auto-allowed.
This mirrors the same "never guess, always be conservative when the real
model isn't available" pattern used for text/image moderation elsewhere in
this project — see `model_used` in the response to see which path ran.
"""
import os
import tempfile
import time
from functools import lru_cache
from typing import Dict, Tuple

from app.config import settings

_CV2_AVAILABLE = True
try:
    import cv2  # noqa: F401
except Exception:
    _CV2_AVAILABLE = False


def _ml_available() -> bool:
    if settings.VIDEO_MODEL_MODE == "stub":
        return False
    if settings.VIDEO_MODEL_MODE == "ml":
        return True
    return _CV2_AVAILABLE  # "auto"


def _extract_first_frame_jpeg(video_bytes: bytes) -> bytes:
    import cv2

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name
    try:
        cap = cv2.VideoCapture(tmp_path)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            raise RuntimeError("Could not read a frame from this video")
        success, buf = cv2.imencode(".jpg", frame)
        if not success:
            raise RuntimeError("Could not encode extracted frame")
        return buf.tobytes()
    finally:
        os.unlink(tmp_path)


def moderate_video(video_bytes: bytes) -> Tuple[Dict[str, float], str, float]:
    """Returns (scores, model_used, processing_time_ms). Scores use the same
    {"nsfw": x, "normal": y} schema as image_moderation, sourced from the
    video's first frame when a frame extractor is available."""
    start = time.perf_counter()
    if _ml_available():
        try:
            from app.models.image_moderation import moderate_image
            frame_jpeg = _extract_first_frame_jpeg(video_bytes)
            scores, image_model_used, _ = moderate_image(frame_jpeg)
            elapsed = (time.perf_counter() - start) * 1000
            return scores, f"video-first-frame:{image_model_used}", elapsed
        except Exception:
            pass  # fall through to the manual-review stub below

    # No frame-level score available: sit exactly at the flag threshold so
    # this always routes to human review rather than being auto-allowed.
    elapsed = (time.perf_counter() - start) * 1000
    neutral = settings.THRESHOLD_FLAG
    return {"nsfw": neutral, "normal": 1 - neutral}, "video-stub-manual-review", elapsed
