"""
Language detection: primary path uses `langdetect` (n-gram / naive-bayes based,
pure python, no network needed at runtime). Falls back to a tiny stopword-based
heuristic if langdetect isn't installed, so the pipeline never hard-fails.

Supported downstream languages for routing: en (BERT/Detoxify "unbiased") vs.
fr/es/it/pt/tr/ru (multilingual model). Anything else routed to multilingual
as the safer general-purpose default.
"""
from typing import Tuple

_LANGDETECT_AVAILABLE = True
try:
    from langdetect import DetectorFactory, detect_langs

    DetectorFactory.seed = 0  # deterministic results
except Exception:  # pragma: no cover - exercised when dependency missing
    _LANGDETECT_AVAILABLE = False

MULTILINGUAL_LANGS = {"fr", "es", "it", "pt", "tr", "ru"}

# Tiny heuristic fallback: a handful of very common stopwords per language.
_STOPWORDS = {
    "en": {"the", "is", "and", "you", "are", "this", "that", "to", "of"},
    "fr": {"le", "la", "les", "et", "vous", "est", "que", "des", "un", "une"},
    "es": {"el", "la", "los", "las", "y", "usted", "es", "que", "un", "una"},
    "it": {"il", "la", "le", "e", "sei", "questo", "che", "un", "una"},
    "pt": {"o", "a", "os", "as", "e", "voce", "esse", "que", "um", "uma"},
    "tr": {"ve", "bu", "bir", "sen", "icin", "de", "da"},
    "ru": {"и", "вы", "это", "что", "не", "на", "в"},
}


def _heuristic_detect(text: str) -> Tuple[str, float]:
    words = set(w.strip(".,!?;:\"'()").lower() for w in text.split())
    best_lang, best_score = "en", 0.0
    for lang, stop in _STOPWORDS.items():
        overlap = len(words & stop)
        if overlap > best_score:
            best_score = overlap
            best_lang = lang
    confidence = min(1.0, 0.4 + 0.15 * best_score) if best_score > 0 else 0.3
    return best_lang, confidence


def detect_language(text: str) -> Tuple[str, float, str]:
    """
    Returns (lang_code, confidence, detector_used).
    detector_used is "langdetect" or "heuristic-fallback".
    """
    text = (text or "").strip()
    if not text:
        return "en", 0.0, "default"

    if _LANGDETECT_AVAILABLE:
        try:
            candidates = detect_langs(text)
            top = candidates[0]
            return top.lang, float(top.prob), "langdetect"
        except Exception:
            pass  # fall through to heuristic

    lang, conf = _heuristic_detect(text)
    return lang, conf, "heuristic-fallback"


def route_for_language(lang: str) -> str:
    """Returns 'en' or 'multilingual' routing bucket for the text model."""
    if lang == "en":
        return "en"
    if lang in MULTILINGUAL_LANGS:
        return "multilingual"
    # Unknown/other language -> safest default is the multilingual model
    return "multilingual"
