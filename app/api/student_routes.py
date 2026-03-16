"""
Student Routes
POST /submit-answer        — Submit answer, update adaptive difficulty, update streak
GET  /students/{id}/dashboard — Learning dashboard with stats & streaks
POST /bookmarks            — Bookmark a question
DELETE /bookmarks          — Remove bookmark
GET  /students/{id}/bookmarks — Get bookmarked questions
GET  /students/{id}/weak-areas — Identify weakest topics
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.database_models import (
    Bookmark,
    Question,
    StudentAnswer,
    StudentProfile,
)
from app.models.schemas import (
    BookmarkRequest,
    BookmarkResponse,
    StudentDashboard,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.services.adaptive_engine import get_next_difficulty, update_streak

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_or_create_student(db: Session, student_id: str) -> StudentProfile:
    student = db.query(StudentProfile).filter(StudentProfile.student_id == student_id).first()
    if not student:
        student = StudentProfile(
            id=str(uuid.uuid4()),
            student_id=student_id,
            current_difficulty="easy",
        )
        db.add(student)
        db.flush()
    return student


@router.post("/submit-answer", response_model=SubmitAnswerResponse, summary="Submit a student's answer")
def submit_answer(req: SubmitAnswerRequest, db: Session = Depends(get_db)):
    """
    Submit a student's answer to a question.
    
    - Checks correctness
    - Updates student profile (accuracy, streak, difficulty)
    - Runs adaptive difficulty algorithm
    - Returns feedback with new difficulty recommendation
    """
    # Get question
    q = db.query(Question).filter(Question.id == req.question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found.")

    # Check correctness (case-insensitive)
    is_correct = req.selected_answer.strip().lower() == q.answer.strip().lower()

    # Get or create student profile
    student = _get_or_create_student(db, req.student_id)

    # Record answer
    answer_record = StudentAnswer(
        id=str(uuid.uuid4()),
        student_id=req.student_id,
        question_id=req.question_id,
        selected_answer=req.selected_answer,
        is_correct=is_correct,
        time_taken_seconds=req.time_taken_seconds,
        difficulty_at_attempt=student.current_difficulty,
        hint_used=req.hint_used,
    )
    db.add(answer_record)

    # Update question stats
    q.times_attempted += 1
    if is_correct:
        q.times_correct += 1

    # Update student profile
    student.total_attempted += 1
    if is_correct:
        student.total_correct += 1

    # Update streaks
    new_streak, _ = update_streak(student.streak_current, is_correct)
    student.streak_current = new_streak
    if new_streak > student.streak_best:
        student.streak_best = new_streak

    # Get recent answer history for adaptive engine
    recent = (
        db.query(StudentAnswer.is_correct)
        .filter(StudentAnswer.student_id == req.student_id)
        .order_by(StudentAnswer.submitted_at.desc())
        .limit(20)
        .all()
    )
    recent_bools = [r[0] for r in recent]

    # Calculate new difficulty
    new_difficulty, diff_message = get_next_difficulty(
        current_difficulty=student.current_difficulty,
        recent_answers=list(reversed(recent_bools)),
        streak_correct=student.streak_current,
    )
    student.current_difficulty = new_difficulty
    student.last_active = datetime.utcnow()

    db.commit()

    return SubmitAnswerResponse(
        is_correct=is_correct,
        correct_answer=q.answer,
        explanation=None,
        new_difficulty=new_difficulty,
        difficulty_message=diff_message,
        streak=student.streak_current,
        accuracy=student.accuracy,
    )


@router.get("/students/{student_id}/dashboard", response_model=StudentDashboard, summary="Student learning dashboard")
def student_dashboard(student_id: str, db: Session = Depends(get_db)):
    """
    Full learning dashboard for a student:
    - Overall stats and accuracy
    - Current streak & best streak
    - Recent performance (last 10 answers)
    - Subject breakdown
    - Bookmarked question count
    """
    student = db.query(StudentProfile).filter(StudentProfile.student_id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found. Submit an answer first to auto-create profile.")

    # Recent 10 answers
    recent_answers = (
        db.query(StudentAnswer, Question)
        .join(Question, StudentAnswer.question_id == Question.id)
        .filter(StudentAnswer.student_id == student_id)
        .order_by(StudentAnswer.submitted_at.desc())
        .limit(10)
        .all()
    )

    recent_performance = [
        {
            "question": q.question[:80] + "..." if len(q.question) > 80 else q.question,
            "subject": q.subject,
            "difficulty": a.difficulty_at_attempt,
            "correct": a.is_correct,
            "time_seconds": a.time_taken_seconds,
            "submitted_at": a.submitted_at,
        }
        for a, q in recent_answers
    ]

    # Subject breakdown — case/when works on both SQLite and PostgreSQL
    from sqlalchemy import case as sa_case
    subject_stats = (
        db.query(
            Question.subject,
            func.count(StudentAnswer.id).label("total"),
            func.sum(
                sa_case((StudentAnswer.is_correct == True, 1), else_=0)
            ).label("correct"),
        )
        .join(Question, StudentAnswer.question_id == Question.id)
        .filter(StudentAnswer.student_id == student_id)
        .group_by(Question.subject)
        .all()
    )

    subject_breakdown = [
        {
            "subject": s or "Unknown",
            "total": t,
            "correct": int(c or 0),
            "accuracy": round(int(c or 0) / t * 100, 1) if t > 0 else 0,
        }
        for s, t, c in subject_stats
    ]

    # Bookmark count
    bookmark_count = db.query(func.count(Bookmark.id)).filter(Bookmark.student_id == student_id).scalar()

    return StudentDashboard(
        student_id=student.student_id,
        display_name=student.display_name,
        current_difficulty=student.current_difficulty,
        total_attempted=student.total_attempted,
        total_correct=student.total_correct,
        accuracy=student.accuracy,
        streak_current=student.streak_current,
        streak_best=student.streak_best,
        last_active=student.last_active,
        recent_performance=recent_performance,
        subject_breakdown=subject_breakdown,
        bookmarked_count=bookmark_count or 0,
    )


@router.get("/students/{student_id}/weak-areas", summary="Identify student's weakest topics")
def weak_areas(student_id: str, db: Session = Depends(get_db)):
    """
    Identify topics where the student struggles most (accuracy < 50%).
    Great for suggesting which bookmarks to revisit.
    """
    stats = (
        db.query(
            Question.topic,
            Question.subject,
            func.count(StudentAnswer.id).label("total"),
        )
        .join(Question, StudentAnswer.question_id == Question.id)
        .filter(StudentAnswer.student_id == student_id)
        .group_by(Question.topic, Question.subject)
        .having(func.count(StudentAnswer.id) >= 3)
        .all()
    )

    weak = []
    for topic, subject, total in stats:
        correct = (
            db.query(func.count(StudentAnswer.id))
            .join(Question, StudentAnswer.question_id == Question.id)
            .filter(
                StudentAnswer.student_id == student_id,
                StudentAnswer.is_correct == True,
                Question.topic == topic,
            )
            .scalar()
        )
        accuracy = round((correct or 0) / total * 100, 1)
        if accuracy < 60:
            weak.append({"topic": topic, "subject": subject, "accuracy": accuracy, "total_attempted": total})

    weak.sort(key=lambda x: x["accuracy"])
    return {"student_id": student_id, "weak_areas": weak}


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------

@router.post("/bookmarks", response_model=BookmarkResponse, summary="Bookmark a question")
def bookmark_question(req: BookmarkRequest, db: Session = Depends(get_db)):
    """
    Bookmark a question for later review.
    Students can add personal notes to bookmarks.
    """
    q = db.query(Question).filter(Question.id == req.question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found.")

    student = _get_or_create_student(db, req.student_id)

    existing = (
        db.query(Bookmark)
        .filter(Bookmark.student_id == req.student_id, Bookmark.question_id == req.question_id)
        .first()
    )

    if existing:
        existing.note = req.note
        db.commit()
        return BookmarkResponse(bookmarked=True, question_id=req.question_id, message="Bookmark updated.")

    bm = Bookmark(
        id=str(uuid.uuid4()),
        student_id=req.student_id,
        question_id=req.question_id,
        note=req.note,
    )
    db.add(bm)
    db.commit()
    return BookmarkResponse(bookmarked=True, question_id=req.question_id, message="Question bookmarked successfully.")


@router.delete("/bookmarks", response_model=BookmarkResponse, summary="Remove a bookmark")
def remove_bookmark(student_id: str, question_id: str, db: Session = Depends(get_db)):
    """Remove a bookmarked question."""
    bm = (
        db.query(Bookmark)
        .filter(Bookmark.student_id == student_id, Bookmark.question_id == question_id)
        .first()
    )
    if not bm:
        raise HTTPException(status_code=404, detail="Bookmark not found.")
    db.delete(bm)
    db.commit()
    return BookmarkResponse(bookmarked=False, question_id=question_id, message="Bookmark removed.")


@router.get("/students/{student_id}/bookmarks", summary="Get student's bookmarked questions")
def get_bookmarks(student_id: str, db: Session = Depends(get_db)):
    """Return all bookmarked questions for a student, with their personal notes."""
    bookmarks = (
        db.query(Bookmark, Question)
        .join(Question, Bookmark.question_id == Question.id)
        .filter(Bookmark.student_id == student_id)
        .order_by(Bookmark.bookmarked_at.desc())
        .all()
    )

    return {
        "student_id": student_id,
        "total": len(bookmarks),
        "bookmarks": [
            {
                "bookmark_id": bm.id,
                "note": bm.note,
                "bookmarked_at": bm.bookmarked_at,
                "question": {
                    "id": q.id,
                    "question": q.question,
                    "type": q.question_type,
                    "options": q.options,
                    "difficulty": q.difficulty,
                    "topic": q.topic,
                    "subject": q.subject,
                },
            }
            for bm, q in bookmarks
        ],
    }
