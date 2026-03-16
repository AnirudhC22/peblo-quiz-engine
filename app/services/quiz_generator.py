"""
Quiz Generator Service
- Generates MCQ, True/False, and Fill-in-the-blank questions using LLM
- Validates questions (answer in options, proper format)
- Detects near-duplicate questions using simple cosine similarity on word sets
- Attaches source traceability (chunk_id, topic, subject, grade)
"""

import json
import logging
import math
import re
from typing import Optional

from app.services.llm_client import call_llm_json

logger = logging.getLogger(__name__)

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

QUIZ_SYSTEM = """You are an expert educational quiz designer for K-12 students.
Your job is to generate clear, age-appropriate quiz questions from educational text.
Always respond with valid JSON only — no preamble, no explanation, no markdown fences."""


def _build_quiz_prompt(text: str, subject: str, grade: int, topic: Optional[str], difficulty: str, num_questions: int) -> str:
    grade_note = f"Grade {grade}" if grade else "Elementary"
    topic_note = f"Topic: {topic}" if topic else ""

    return f"""Generate {num_questions} quiz questions from the educational text below.

Context:
- Subject: {subject}
- Level: {grade_note}
- Difficulty: {difficulty}
{topic_note}

Text:
\"\"\"
{text}
\"\"\"

Generate a mix of question types: MCQ (multiple choice), TrueFalse, FillBlank.
For MCQ: provide exactly 4 options.
For TrueFalse: options must be ["True", "False"].
For FillBlank: question must contain "___" and answer fills the blank.

Difficulty guidelines:
- easy: recall facts directly stated in text
- medium: requires understanding/inference
- hard: requires synthesis or application

Return a JSON array like:
[
  {{
    "question": "How many sides does a triangle have?",
    "type": "MCQ",
    "options": ["2", "3", "4", "5"],
    "answer": "3",
    "difficulty": "{difficulty}"
  }},
  {{
    "question": "A triangle has three sides.",
    "type": "TrueFalse",
    "options": ["True", "False"],
    "answer": "True",
    "difficulty": "{difficulty}"
  }},
  {{
    "question": "A triangle has ___ sides.",
    "type": "FillBlank",
    "options": [],
    "answer": "three",
    "difficulty": "{difficulty}"
  }}
]

Return ONLY the JSON array."""


HINT_SYSTEM = """You are a helpful tutor for K-12 students. 
Give a short, encouraging hint that guides the student toward the answer WITHOUT revealing it.
Keep hints to 1-2 sentences. Be friendly and age-appropriate."""


def _build_hint_prompt(question: str, answer: str, subject: str) -> str:
    return f"""A student is stuck on this {subject} question:

Question: {question}
Correct answer: {answer}

Give a helpful hint that nudges them toward the answer without giving it away."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_question(q: dict) -> tuple[bool, float]:
    """
    Validate a generated question.
    Returns (is_valid, quality_score 0.0–1.0)
    """
    required = {"question", "type", "answer", "difficulty"}
    if not required.issubset(q.keys()):
        return False, 0.0

    q_type = q.get("type")
    options = q.get("options", [])
    answer = str(q.get("answer", "")).strip()
    question_text = q.get("question", "").strip()
    difficulty = q.get("difficulty", "")

    if not question_text or not answer:
        return False, 0.0

    if difficulty not in DIFFICULTY_LEVELS:
        return False, 0.0

    score = 1.0

    if q_type == "MCQ":
        if len(options) != 4:
            return False, 0.0
        if answer not in options:
            return False, 0.0

    elif q_type == "TrueFalse":
        if set(options) != {"True", "False"}:
            return False, 0.0
        if answer not in ["True", "False"]:
            return False, 0.0

    elif q_type == "FillBlank":
        if "___" not in question_text:
            score -= 0.1  # soft penalty — still usable

    # Penalize very short questions
    if len(question_text.split()) < 4:
        score -= 0.2

    return True, round(max(0.1, score), 2)


# ---------------------------------------------------------------------------
# Duplicate detection (cosine similarity on word sets)
# ---------------------------------------------------------------------------

def _word_vector(text: str) -> dict[str, float]:
    words = re.findall(r"\w+", text.lower())
    vec: dict[str, float] = {}
    for w in words:
        vec[w] = vec.get(w, 0) + 1
    return vec


def _cosine_similarity(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v ** 2 for v in a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def deduplicate_questions(new_questions: list[dict], existing_questions: list[str], threshold: float = 0.85) -> list[dict]:
    """
    Remove questions too similar to existing ones.
    existing_questions: list of question text strings already in DB.
    """
    existing_vecs = [_word_vector(q) for q in existing_questions]
    accepted = []

    for q in new_questions:
        q_vec = _word_vector(q["question"])
        is_duplicate = False

        for ev in existing_vecs:
            if _cosine_similarity(q_vec, ev) >= threshold:
                is_duplicate = True
                logger.info(f"Duplicate detected: {q['question'][:60]}...")
                break

        if not is_duplicate:
            accepted.append(q)
            existing_vecs.append(q_vec)  # also check against newly accepted

    logger.info(f"Deduplication: {len(new_questions)} in → {len(accepted)} accepted")
    return accepted


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

def generate_questions(
    chunk_text: str,
    chunk_id: str,
    subject: str,
    grade: int,
    topic: Optional[str],
    difficulty: str = "easy",
    num_questions: int = 5,
    existing_question_texts: Optional[list[str]] = None,
) -> list[dict]:
    """
    Generate validated, deduplicated quiz questions from a chunk.
    Returns list of question dicts ready for DB insertion.
    """
    prompt = _build_quiz_prompt(chunk_text, subject, grade, topic, difficulty, num_questions)

    try:
        raw = call_llm_json(prompt, QUIZ_SYSTEM)
    except Exception as e:
        logger.error(f"LLM generation failed for chunk {chunk_id}: {e}")
        return []

    if not isinstance(raw, list):
        logger.error(f"LLM returned non-list for chunk {chunk_id}: {type(raw)}")
        return []

    # Validate each question
    validated = []
    for q in raw:
        is_valid, quality = _validate_question(q)
        if is_valid:
            q["quality_score"] = quality
            validated.append(q)
        else:
            logger.warning(f"Question failed validation: {q.get('question', '')[:60]}")

    logger.info(f"Chunk {chunk_id}: {len(raw)} generated → {len(validated)} valid")

    # Deduplicate against existing
    if existing_question_texts:
        validated = deduplicate_questions(validated, existing_question_texts)

    # Attach traceability metadata
    for q in validated:
        q["chunk_id"] = chunk_id
        q["topic"] = topic
        q["subject"] = subject
        q["grade"] = grade

    return validated


# ---------------------------------------------------------------------------
# Hint generation
# ---------------------------------------------------------------------------

def generate_hint(question: str, answer: str, subject: str) -> str:
    """Generate an AI hint for a student without revealing the answer."""
    from app.services.llm_client import call_llm
    prompt = _build_hint_prompt(question, answer, subject)
    try:
        hint = call_llm(prompt, HINT_SYSTEM, max_tokens=200)
        return hint.strip()
    except Exception as e:
        logger.error(f"Hint generation failed: {e}")
        return "Think carefully about what you've learned. You can do it!"
