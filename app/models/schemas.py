"""
Pydantic Schemas — Request and Response models for all API endpoints.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class IngestResponse(BaseModel):
    document_id: str
    file_name: str
    subject: str
    grade: int
    total_pages: int
    chunks_created: int
    message: str


# ---------------------------------------------------------------------------
# Quiz Generation
# ---------------------------------------------------------------------------

class GenerateQuizRequest(BaseModel):
    document_id: Optional[str] = Field(None, description="Generate from specific document")
    topic: Optional[str] = Field(None, description="Filter by topic keyword")
    subject: Optional[str] = Field(None, description="Filter by subject")
    difficulty: Optional[str] = Field("easy", description="easy | medium | hard")
    questions_per_chunk: int = Field(3, ge=1, le=10, description="Questions per chunk")

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "uuid-here",
                "topic": "shapes",
                "difficulty": "easy",
                "questions_per_chunk": 3,
            }
        }


class GenerateQuizResponse(BaseModel):
    job_id: str
    document_id: Optional[str]
    questions_generated: int
    message: str


# ---------------------------------------------------------------------------
# Quiz Retrieval (student customizer)
# ---------------------------------------------------------------------------

class QuizCustomizerRequest(BaseModel):
    topic: Optional[str] = Field(None, description="Topic to filter questions")
    subject: Optional[str] = Field(None, description="Subject filter")
    grade: Optional[int] = Field(None, description="Grade level filter")
    difficulty: Optional[str] = Field(None, description="easy | medium | hard | auto")
    question_types: Optional[list[str]] = Field(None, description="MCQ, TrueFalse, FillBlank")
    num_questions: int = Field(10, ge=1, le=50, description="Number of questions to fetch")
    student_id: Optional[str] = Field(None, description="If provided, uses adaptive difficulty")
    exclude_attempted: bool = Field(False, description="Skip questions already answered by student")
    bookmarked_only: bool = Field(False, description="Only return bookmarked questions")

    class Config:
        json_schema_extra = {
            "example": {
                "topic": "shapes",
                "difficulty": "auto",
                "num_questions": 10,
                "student_id": "S001",
                "exclude_attempted": True,
            }
        }


class QuestionOut(BaseModel):
    id: str
    question: str
    type: str
    options: list[str]
    difficulty: str
    topic: Optional[str]
    subject: Optional[str]
    grade: Optional[int]
    chunk_id: str
    success_rate: float

    class Config:
        from_attributes = True


class QuizResponse(BaseModel):
    total: int
    difficulty_used: str
    questions: list[QuestionOut]


# ---------------------------------------------------------------------------
# Answer Submission
# ---------------------------------------------------------------------------

class SubmitAnswerRequest(BaseModel):
    student_id: str
    question_id: str
    selected_answer: str
    time_taken_seconds: Optional[int] = None
    hint_used: bool = False

    class Config:
        json_schema_extra = {
            "example": {
                "student_id": "S001",
                "question_id": "uuid-here",
                "selected_answer": "3",
                "time_taken_seconds": 15,
                "hint_used": False,
            }
        }


class SubmitAnswerResponse(BaseModel):
    is_correct: bool
    correct_answer: str
    explanation: Optional[str] = None
    new_difficulty: str
    difficulty_message: str
    streak: int
    accuracy: float


# ---------------------------------------------------------------------------
# Hint
# ---------------------------------------------------------------------------

class HintResponse(BaseModel):
    question_id: str
    hint: str


# ---------------------------------------------------------------------------
# Bookmark
# ---------------------------------------------------------------------------

class BookmarkRequest(BaseModel):
    student_id: str
    question_id: str
    note: Optional[str] = None


class BookmarkResponse(BaseModel):
    bookmarked: bool
    question_id: str
    message: str


# ---------------------------------------------------------------------------
# Student Profile / Dashboard
# ---------------------------------------------------------------------------

class StudentDashboard(BaseModel):
    student_id: str
    display_name: Optional[str]
    current_difficulty: str
    total_attempted: int
    total_correct: int
    accuracy: float
    streak_current: int
    streak_best: int
    last_active: Optional[datetime]
    recent_performance: list[dict]
    subject_breakdown: list[dict]
    bookmarked_count: int
