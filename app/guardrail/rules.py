"""
Guardrail decision policy.

Decision logic (env-driven thresholds, both 0.0-1.0):
  any category >= THRESHOLD_BLOCK -> "block"
  else any category >= THRESHOLD_FLAG -> "flag"
  else -> "allow"
"""
from typing import Dict, List, Tuple

from app.config import settings


def decide(scores: Dict[str, float]) -> Tuple[str, List[str]]:
    flag_t = settings.THRESHOLD_FLAG
    block_t = settings.THRESHOLD_BLOCK

    block_reasons = [f"{cat}={val:.3f} >= block threshold {block_t:.2f}"
                      for cat, val in scores.items() if val >= block_t]
    if block_reasons:
        return "block", block_reasons

    flag_reasons = [f"{cat}={val:.3f} >= flag threshold {flag_t:.2f}"
                     for cat, val in scores.items() if val >= flag_t]
    if flag_reasons:
        return "flag", flag_reasons

    return "allow", ["all categories below flag threshold"]
