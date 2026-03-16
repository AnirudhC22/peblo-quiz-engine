"""
Quiz Routes
POST /generate-quiz — Generate questions from stored chunks using LLM
GET  /quiz          — Student quiz customizer (filter by topic, difficulty, grade, etc.)
GET  /quiz/{id}/hint — Get AI hint for a question
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.database_models import Chunk, Document, GenerationJob, Question, StudentProfile, Bookmark
from app.models.schemas import (
    GenerateQuizRequest,
    GenerateQuizResponse,
    HintResponse,
    QuestionOut,
    QuizCustomizerRequest,
    QuizResponse,
)
from app.services.adaptive_engine import suggest_next_question_difficulty
from app.services.quiz_generator import generate_hint, generate_questions

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Background quiz generation
# ---------------------------------------------------------------------------

def _run_generation(job_id: str, document_id: Optional[str], topic: Optional[str], difficulty: str, questions_per_chunk: int, db_url: str):
    """Background task: generate questions and store them."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.database_models import Base

    engine = create_engine(db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {})
    LocalSession = sessionmaker(bind=engine)
    db = LocalSession()

    try:
        # Update job status
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()

        # Find target chunks
        query = db.query(Chunk)
        if document_id:
            query = query.filter(Chunk.document_id == document_id)
        if topic:
            query = query.filter(Chunk.topic.ilike(f"%{topic}%"))
        chunks = query.all()

        if not chunks:
            job.status = "failed"
            job.error_message = "No chunks found matching criteria."
            db.commit()
            return

        # Get existing questions for deduplication
        existing_texts = [q.question for q in db.query(Question.question).all()]

        total_generated = 0
        for chunk in chunks:
            # Get document metadata
            doc = db.query(Document).filter(Document.id == chunk.document_id).first()
            subject = doc.subject if doc else "General"
            grade = doc.grade if doc else 1

            questions = generate_questions(
                chunk_text=chunk.text,
                chunk_id=chunk.id,
                subject=subject,
                grade=grade,
                topic=chunk.topic,
                difficulty=difficulty,
                num_questions=questions_per_chunk,
                existing_question_texts=existing_texts,
            )

            for q in questions:
                q_obj = Question(
                    id=str(uuid.uuid4()),
                    chunk_id=q["chunk_id"],
                    question=q["question"],
                    question_type=q["type"],
                    options_json=json.dumps(q.get("options", [])),
                    answer=q["answer"],
                    difficulty=q["difficulty"],
                    topic=q.get("topic"),
                    subject=q.get("subject"),
                    grade=q.get("grade"),
                    quality_score=q.get("quality_score", 1.0),
                )
                db.add(q_obj)
                existing_texts.append(q["question"])
                total_generated += 1

            db.commit()

        job.status = "done"
        job.questions_generated = total_generated
        job.completed_at = datetime.utcnow()
        db.commit()
        logger.info(f"Job {job_id} completed: {total_generated} questions generated")

    except Exception as e:
        logger.error(f"Generation job {job_id} failed: {e}", exc_info=True)
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
    finally:
        db.close()


@router.post("/generate-quiz", response_model=GenerateQuizResponse, summary="Generate quiz questions using LLM")
async def generate_quiz(
    req: GenerateQuizRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Trigger LLM-powered quiz question generation from stored chunks.
    Runs as a background task — returns job_id immediately.
    """
    import os

    # Validate document if provided
    if req.document_id:
        doc = db.query(Document).filter(Document.id == req.document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")

    job_id = str(uuid.uuid4())
    difficulty = req.difficulty or "easy"

    job = GenerationJob(
        id=job_id,
        document_id=req.document_id,
        topic=req.topic,
        difficulty=difficulty,
        status="queued",
    )
    db.add(job)
    db.commit()

    db_url = os.getenv("DATABASE_URL", "sqlite:///./peblo_quiz.db")

    background_tasks.add_task(
        _run_generation,
        job_id=job_id,
        document_id=req.document_id,
        topic=req.topic,
        difficulty=difficulty,
        questions_per_chunk=req.questions_per_chunk,
        db_url=db_url,
    )

    return GenerateQuizResponse(
        job_id=job_id,
        document_id=req.document_id,
        questions_generated=0,
        message="Quiz generation started. Poll /jobs/{job_id} for status.",
    )


@router.get("/jobs/{job_id}", summary="Check generation job status")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Poll this endpoint to check if question generation has completed."""
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "job_id": job.id,
        "status": job.status,
        "questions_generated": job.questions_generated,
        "error": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


# ---------------------------------------------------------------------------
# Quiz Retrieval — Student Customizer
# ---------------------------------------------------------------------------

@router.get("/quiz", response_model=QuizResponse, summary="Get quiz questions (student customizer)")
def get_quiz(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    subject: Optional[str] = Query(None, description="Filter by subject"),
    grade: Optional[int] = Query(None, description="Filter by grade level"),
    difficulty: Optional[str] = Query(None, description="easy | medium | hard | auto"),
    question_types: Optional[str] = Query(None, description="Comma-separated: MCQ,TrueFalse,FillBlank"),
    num_questions: int = Query(10, ge=1, le=50),
    student_id: Optional[str] = Query(None, description="Enables adaptive difficulty"),
    exclude_attempted: bool = Query(False, description="Skip already-answered questions"),
    bookmarked_only: bool = Query(False, description="Only bookmarked questions"),
    db: Session = Depends(get_db),
):
    """
    Flexible quiz retrieval with student customization options.
    
    - Filter by topic, subject, grade, difficulty, question type
    - Set difficulty='auto' to use adaptive difficulty for the student
    - Exclude already-attempted questions
    - Return only bookmarked/weak questions
    """
    # Resolve adaptive difficulty
    resolved_difficulty = difficulty
    student = None

    if student_id:
        student = db.query(StudentProfile).filter(StudentProfile.student_id == student_id).first()

    if difficulty == "auto" or difficulty is None:
        if student:
            resolved_difficulty = suggest_next_question_difficulty(student.accuracy, student.current_difficulty)
        else:
            resolved_difficulty = "easy"

    # Build query
    query = db.query(Question).filter(Question.is_duplicate == False)

    if resolved_difficulty and resolved_difficulty != "auto":
        query = query.filter(Question.difficulty == resolved_difficulty)

    if topic:
        query = query.filter(Question.topic.ilike(f"%{topic}%"))

    if subject:
        query = query.filter(Question.subject.ilike(f"%{subject}%"))

    if grade:
        query = query.filter(Question.grade == grade)

    if question_types:
        types = [t.strip() for t in question_types.split(",")]
        query = query.filter(Question.question_type.in_(types))

    # Exclude already attempted
    if exclude_attempted and student_id:
        from app.models.database_models import StudentAnswer
        attempted_ids = [
            r[0] for r in db.query(StudentAnswer.question_id)
            .filter(StudentAnswer.student_id == student_id)
            .all()
        ]
        if attempted_ids:
            query = query.filter(~Question.id.in_(attempted_ids))

    # Bookmarked only
    if bookmarked_only and student_id:
        bookmarked_ids = [
            r[0] for r in db.query(Bookmark.question_id)
            .filter(Bookmark.student_id == student_id)
            .all()
        ]
        if bookmarked_ids:
            query = query.filter(Question.id.in_(bookmarked_ids))
        else:
            return QuizResponse(total=0, difficulty_used=resolved_difficulty or "easy", questions=[])

    # Random sample
    questions = query.order_by(func.random()).limit(num_questions).all()

    return QuizResponse(
        total=len(questions),
        difficulty_used=resolved_difficulty or "easy",
        questions=[
            QuestionOut(
                id=q.id,
                question=q.question,
                type=q.question_type,
                options=q.options,
                difficulty=q.difficulty,
                topic=q.topic,
                subject=q.subject,
                grade=q.grade,
                chunk_id=q.chunk_id,
                success_rate=q.success_rate,
            )
            for q in questions
        ],
    )


@router.get("/quiz/{question_id}/hint", response_model=HintResponse, summary="Get AI hint for a question")
def get_hint(question_id: str, db: Session = Depends(get_db)):
    """
    Get a contextual AI-generated hint that guides without giving away the answer.
    """
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found.")

    hint = generate_hint(q.question, q.answer, q.subject or "General")
    return HintResponse(question_id=question_id, hint=hint)


@router.get("/questions/stats", summary="Question statistics overview")
def question_stats(db: Session = Depends(get_db)):
    """Overview of all generated questions broken down by difficulty, type, subject."""
    total = db.query(func.count(Question.id)).scalar()
    by_difficulty = (
        db.query(Question.difficulty, func.count(Question.id))
        .group_by(Question.difficulty)
        .all()
    )
    by_type = (
        db.query(Question.question_type, func.count(Question.id))
        .group_by(Question.question_type)
        .all()
    )
    by_subject = (
        db.query(Question.subject, func.count(Question.id))
        .group_by(Question.subject)
        .all()
    )
    return {
        "total_questions": total,
        "by_difficulty": dict(by_difficulty),
        "by_type": dict(by_type),
        "by_subject": dict(by_subject),
    }
