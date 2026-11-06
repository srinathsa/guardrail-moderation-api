"""
Image NSFW classification.

Real path: Hugging Face ViT model (default Falconsai/nsfw_image_detection),
loaded directly via AutoImageProcessor + AutoModelForImageClassification.
We deliberately avoid `transformers.pipeline()` here: the generic pipeline
factory eagerly imports a broad set of task-related code (including
TensorFlow-backed pipelines) which can crash at import time on environments
with mismatched TF/protobuf versions, even though we never use TF. Loading
the processor/model classes directly sidesteps that import graph entirely.

Fallback path: a simple, dependency-free PIL heuristic (skin-tone pixel
ratio) that produces the same 2-category schema so the endpoint keeps
working end-to-end without torch/transformers or model weights.
"""
import io
import time
from functools import lru_cache
from typing import Dict, Tuple

from app.config import settings

_TRANSFORMERS_AVAILABLE = True
try:
    import torch  # noqa: F401
    from transformers import AutoImageProcessor, AutoModelForImageClassification  # noqa: F401
    from PIL import Image  # noqa: F401
except Exception:
    _TRANSFORMERS_AVAILABLE = False

try:
    from PIL import Image  # ensure available even if transformers import failed
except Exception:
    Image = None


def _ml_available() -> bool:
    if settings.IMAGE_MODEL_MODE == "stub":
        return False
    if settings.IMAGE_MODEL_MODE == "ml":
        return True
    return _TRANSFORMERS_AVAILABLE  # "auto"


@lru_cache(maxsize=1)
def _get_processor_and_model():
    from transformers import AutoImageProcessor, AutoModelForImageClassification
    processor = AutoImageProcessor.from_pretrained(settings.HF_IMAGE_MODEL)
    model = AutoModelForImageClassification.from_pretrained(settings.HF_IMAGE_MODEL)
    model.eval()
    return processor, model


def _ml_classify(image_bytes: bytes) -> Dict[str, float]:
    import torch
    from PIL import Image as PILImage

    processor, model = _get_processor_and_model()
    img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.nn.functional.softmax(logits, dim=-1)[0]
    id2label = model.config.id2label
    scores = {id2label[i].lower(): float(probs[i]) for i in range(len(probs))}
    # Normalize label names to our schema: nsfw / normal
    nsfw_score = scores.get("nsfw", max(scores.values()) if "normal" not in scores else 1 - scores.get("normal", 0))
    normal_score = scores.get("normal", 1 - nsfw_score)
    return {"nsfw": nsfw_score, "normal": normal_score}


def _heuristic_classify(image_bytes: bytes) -> Dict[str, float]:
    """Very rough skin-tone-ratio heuristic; NOT a real safety filter — a
    placeholder to keep the API functional without heavy ML dependencies."""
    if Image is None:
        # Can't even open the image; return a neutral low-confidence score.
        return {"nsfw": 0.05, "normal": 0.95}
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img.thumbnail((128, 128))
        pixels = list(img.getdata())
        if not pixels:
            return {"nsfw": 0.05, "normal": 0.95}
        skin_count = 0
        for r, g, b in pixels:
            if r > 95 and g > 40 and b > 20 and (max(r, g, b) - min(r, g, b)) > 15 and r > g and r > b:
                skin_count += 1
        ratio = skin_count / len(pixels)
        nsfw = min(0.95, max(0.02, (ratio - 0.35) * 1.8)) if ratio > 0.35 else 0.05
        return {"nsfw": nsfw, "normal": 1 - nsfw}
    except Exception:
        return {"nsfw": 0.05, "normal": 0.95}


def moderate_image(image_bytes: bytes) -> Tuple[Dict[str, float], str, float]:
    """Returns (scores, model_used, processing_time_ms)."""
    start = time.perf_counter()
    if _ml_available():
        try:
            scores = _ml_classify(image_bytes)
            elapsed = (time.perf_counter() - start) * 1000
            return scores, f"hf-vit-{settings.HF_IMAGE_MODEL.split('/')[-1]}", elapsed
        except Exception:
            pass  # fall through to heuristic on any runtime failure

    scores = _heuristic_classify(image_bytes)
    elapsed = (time.perf_counter() - start) * 1000
    return scores, "heuristic-stub", elapsed
