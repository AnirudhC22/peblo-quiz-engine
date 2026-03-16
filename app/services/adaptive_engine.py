"""
Adaptive Difficulty Engine
Adjusts quiz difficulty based on rolling student performance.

Algorithm:
- Track a rolling window of last N answers
- accuracy >= 80% → promote to harder level
- accuracy <= 40% → demote to easier level
- 40% < accuracy < 80% → stay at current level
- Streaks: 3 correct in a row → fast-track promotion
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

DIFFICULTY_ORDER = ["easy", "medium", "hard"]
WINDOW_SIZE = 10       # rolling window of last N answers
PROMOTE_THRESHOLD = 0.8
DEMOTE_THRESHOLD = 0.4
STREAK_PROMOTE = 3     # consecutive correct → promote


def get_next_difficulty(
    current_difficulty: str,
    recent_answers: list[bool],    # True=correct, ordered oldest→newest
    streak_correct: int = 0,
) -> tuple[str, str]:
    """
    Calculate next difficulty level.
    Returns (new_difficulty, reason_message).
    """
    current_idx = DIFFICULTY_ORDER.index(current_difficulty) if current_difficulty in DIFFICULTY_ORDER else 0

    # Fast-track: streak promotion
    if streak_correct >= STREAK_PROMOTE and current_idx < len(DIFFICULTY_ORDER) - 1:
        new_diff = DIFFICULTY_ORDER[current_idx + 1]
        return new_diff, f"🔥 {streak_correct} correct in a row! Leveling up to {new_diff}."

    if not recent_answers:
        return current_difficulty, "Not enough data yet."

    window = recent_answers[-WINDOW_SIZE:]
    accuracy = sum(window) / len(window)

    if accuracy >= PROMOTE_THRESHOLD and current_idx < len(DIFFICULTY_ORDER) - 1:
        new_diff = DIFFICULTY_ORDER[current_idx + 1]
        return new_diff, f"Great work! {int(accuracy*100)}% accuracy → moving to {new_diff}."

    elif accuracy <= DEMOTE_THRESHOLD and current_idx > 0:
        new_diff = DIFFICULTY_ORDER[current_idx - 1]
        return new_diff, f"Let's practice more. {int(accuracy*100)}% accuracy → moving to {new_diff}."

    return current_difficulty, f"Staying at {current_difficulty} ({int(accuracy*100)}% accuracy)."


def update_streak(current_streak: int, is_correct: bool) -> tuple[int, int]:
    """
    Update streak counters.
    Returns (new_current_streak, new_best_streak_if_broken).
    """
    if is_correct:
        return current_streak + 1, current_streak + 1
    return 0, 0


def compute_student_stats(answers: list[bool]) -> dict:
    """Compute summary statistics for a student's answer history."""
    if not answers:
        return {"total": 0, "correct": 0, "accuracy": 0.0, "current_streak": 0}

    correct = sum(answers)
    total = len(answers)

    # Compute current streak (from end)
    streak = 0
    for a in reversed(answers):
        if a:
            streak += 1
        else:
            break

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1),
        "current_streak": streak,
    }


def suggest_next_question_difficulty(
    student_accuracy: float,
    current_difficulty: str,
) -> str:
    """
    One-shot suggestion without full history.
    Used for quick adaptive quiz retrieval.
    """
    idx = DIFFICULTY_ORDER.index(current_difficulty) if current_difficulty in DIFFICULTY_ORDER else 0

    if student_accuracy >= 80 and idx < 2:
        return DIFFICULTY_ORDER[idx + 1]
    elif student_accuracy < 40 and idx > 0:
        return DIFFICULTY_ORDER[idx - 1]
    return current_difficulty
