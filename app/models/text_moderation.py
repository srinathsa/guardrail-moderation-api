"""
Text toxicity scoring.

Real path: Detoxify (torch/transformers backed).
  - "original"/"unbiased" checkpoint for English
  - "multilingual" checkpoint (XLM-RoBERTa based) for fr/es/it/pt/tr/ru/other

Fallback path: a deterministic lightweight keyword/pattern heuristic that
produces scores in the same category schema, so the API keeps working
end-to-end when detoxify/torch/transformers aren't installed or model
weights can't be downloaded (e.g. offline dev/CI environments).

Categories (fixed schema regardless of backend):
  toxicity, severe_toxicity, obscene, threat, insult, identity_attack
"""
import re
import time
from functools import lru_cache
from typing import Dict, Tuple

from app.config import settings
from app.models.language_detect import detect_language, route_for_language

CATEGORIES = [
    "toxicity",
    "severe_toxicity",
    "obscene",
    "threat",
    "insult",
    "identity_attack",
]

_DETOXIFY_AVAILABLE = True
try:
    from detoxify import Detoxify  # noqa: F401
except Exception:
    _DETOXIFY_AVAILABLE = False


@lru_cache(maxsize=1)
def _get_english_model():
    from detoxify import Detoxify
    return Detoxify("unbiased")


@lru_cache(maxsize=1)
def _get_multilingual_model():
    from detoxify import Detoxify
    return Detoxify("multilingual")


def _ml_available() -> bool:
    if settings.TEXT_MODEL_MODE == "stub":
        return False
    if settings.TEXT_MODEL_MODE == "ml":
        return True
    return _DETOXIFY_AVAILABLE  # "auto"


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------
_PATTERNS = {
    "obscene": [r"\bf+u+c+k+\w*", r"\bsh[i1]t\w*", r"\bass(hole)?\b", r"\bbitch\w*"],
    "threat": [r"\bkill\s+you\b", r"\bi\s*will\s*(kill|hurt|destroy)\b", r"\bgonna\s+hurt\s+you\b", r"\bdie\b"],
    "insult": [r"\bidiot\b", r"\bstupid\b", r"\bmoron\b", r"\bloser\b", r"\bdumb\w*"],
    "identity_attack": [r"\b(race|religion|gender)\s+slur\b", r"\ball\s+\w+\s+are\s+(stupid|inferior|subhuman)\b"],
    "severe_toxicity": [r"\bsubhuman\b", r"\bdeserve\s+to\s+die\b", r"\bshould\s+be\s+killed\b"],
}
_ALLCAPS_RE = re.compile(r"^[^a-z]*[A-Z]{4,}[^a-z]*$")


def _heuristic_score(text: str) -> Dict[str, float]:
    lowered = text.lower()
    scores = {c: 0.02 for c in CATEGORIES}
    for cat, patterns in _PATTERNS.items():
        hits = sum(len(re.findall(p, lowered)) for p in patterns)
        if hits:
            scores[cat] = min(1.0, 0.55 + 0.2 * hits)
    # toxicity aggregates other signals (matches how real toxicity models behave)
    scores["toxicity"] = max(scores.values())
    if "!" in text and text.count("!") >= 3:
        scores["toxicity"] = min(1.0, scores["toxicity"] + 0.1)
    if _ALLCAPS_RE.match(text.strip()):
        scores["toxicity"] = min(1.0, scores["toxicity"] + 0.1)
    return scores


def moderate_text(text: str) -> Tuple[Dict[str, float], str, str, float]:
    """
    Returns (scores, detected_language, model_used, processing_time_ms)
    """
    start = time.perf_counter()
    lang, _conf, _detector = detect_language(text)
    bucket = route_for_language(lang)

    if _ml_available():
        try:
            model = _get_english_model() if bucket == "en" else _get_multilingual_model()
            raw = model.predict(text)
            scores = {c: float(raw.get(c, 0.0)) for c in CATEGORIES}
            model_used = f"detoxify-{'unbiased' if bucket == 'en' else 'multilingual'}"
            elapsed = (time.perf_counter() - start) * 1000
            return scores, lang, model_used, elapsed
        except Exception:
            pass  # fall through to heuristic on any runtime failure

    scores = _heuristic_score(text)
    model_used = "heuristic-stub"
    elapsed = (time.perf_counter() - start) * 1000
    return scores, lang, model_used, elapsed
