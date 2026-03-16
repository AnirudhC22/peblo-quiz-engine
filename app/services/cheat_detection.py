"""
Cheat Detection Service
Tracks suspicious student behavior during a quiz session:
- Tab switching / window focus loss
- Copy-paste attempts on questions
- Rapid answer submission (too fast to read)
- Idle then sudden answer (possible lookup)
- Right-click / DevTools open attempts

Cheat events are stored per-session and attached to the student profile.
A risk score (0–100) is computed and flagged if > threshold.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Risk scoring weights
RISK_WEIGHTS = {
    "tab_switch": 15,
    "focus_loss": 10,
    "copy_paste": 20,
    "fast_submit": 25,   # answered in < 3 seconds
    "right_click": 5,
    "devtools_open": 30,
    "idle_then_fast": 20,
}

FLAG_THRESHOLD = 50   # risk score above this triggers a flag


def compute_risk_score(events: list[dict]) -> int:
    """Compute cumulative risk score from a list of cheat events."""
    score = 0
    for event in events:
        weight = RISK_WEIGHTS.get(event.get("event_type"), 0)
        score += weight
    return min(score, 100)


def is_fast_submit(time_taken_seconds: Optional[int], question_text: str) -> bool:
    """
    Heuristic: reading speed ~200 wpm → minimum time to read + answer.
    Flag if answer submitted suspiciously fast.
    """
    if time_taken_seconds is None:
        return False
    word_count = len(question_text.split())
    min_read_time = max(3, word_count / 3)   # generous minimum
    return time_taken_seconds < min_read_time
