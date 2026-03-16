"""
Database Models — Full schema with traceability
Document → Chunk → Question → StudentAnswer
"""

import json
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def gen_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Document(Base):
    """Source PDF documents ingested into the system."""
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_id)
    file_name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    grade = Column(Integer, nullable=False)
    total_pages = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending | processed | failed
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete")


class Chunk(Base):
    """Content chunks extracted from documents."""
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    topic = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    word_count = Column(Integer, default=0)
    embedding_cached = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")
    questions = relationship("Question", back_populates="chunk", cascade="all, delete")


class Question(Base):
    """Quiz questions generated from content chunks."""
    __tablename__ = "questions"

    id = Column(String, primary_key=True, default=gen_id)
    chunk_id = Column(String, ForeignKey("chunks.id"), nullable=False)
    question = Column(Text, nullable=False)
    question_type = Column(String, nullable=False)   # MCQ | TrueFalse | FillBlank
    options_json = Column(Text, nullable=True)        # JSON array stored as text
    answer = Column(String, nullable=False)
    difficulty = Column(String, default="easy")       # easy | medium | hard
    topic = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    grade = Column(Integer, nullable=True)
    times_attempted = Column(Integer, default=0)
    times_correct = Column(Integer, default=0)
    quality_score = Column(Float, default=1.0)        # 0.0–1.0 validation score
    is_duplicate = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    chunk = relationship("Chunk", back_populates="questions")
    answers = relationship("StudentAnswer", back_populates="question")
    bookmarks = relationship("Bookmark", back_populates="question", cascade="all, delete")

    @property
    def options(self) -> list:
        if self.options_json:
            return json.loads(self.options_json)
        return []

    @options.setter
    def options(self, value: list):
        self.options_json = json.dumps(value)

    @property
    def success_rate(self) -> float:
        if self.times_attempted == 0:
            return 0.0
        return round(self.times_correct / self.times_attempted, 2)


class StudentProfile(Base):
    """Student profile with adaptive difficulty state."""
    __tablename__ = "student_profiles"

    id = Column(String, primary_key=True, default=gen_id)
    student_id = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    current_difficulty = Column(String, default="easy")  # easy | medium | hard
    total_attempted = Column(Integer, default=0)
    total_correct = Column(Integer, default=0)
    streak_current = Column(Integer, default=0)
    streak_best = Column(Integer, default=0)
    last_active = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    answers = relationship("StudentAnswer", back_populates="student")
    bookmarks = relationship("Bookmark", back_populates="student", cascade="all, delete")

    @property
    def accuracy(self) -> float:
        if self.total_attempted == 0:
            return 0.0
        return round(self.total_correct / self.total_attempted * 100, 1)

    @property
    def computed_difficulty(self) -> str:
        """Smart adaptive difficulty based on rolling accuracy."""
        if self.total_attempted < 5:
            return self.current_difficulty
        acc = self.accuracy
        if acc >= 80:
            return "hard"
        elif acc >= 50:
            return "medium"
        else:
            return "easy"


class StudentAnswer(Base):
    """Individual answer records for full audit trail."""
    __tablename__ = "student_answers"

    id = Column(String, primary_key=True, default=gen_id)
    student_id = Column(String, ForeignKey("student_profiles.student_id"), nullable=False)
    question_id = Column(String, ForeignKey("questions.id"), nullable=False)
    selected_answer = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    time_taken_seconds = Column(Integer, nullable=True)
    difficulty_at_attempt = Column(String, nullable=True)
    hint_used = Column(Boolean, default=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("StudentProfile", back_populates="answers")
    question = relationship("Question", back_populates="answers")


class Bookmark(Base):
    """Student bookmarks for weak/revisit questions."""
    __tablename__ = "bookmarks"

    id = Column(String, primary_key=True, default=gen_id)
    student_id = Column(String, ForeignKey("student_profiles.student_id"), nullable=False)
    question_id = Column(String, ForeignKey("questions.id"), nullable=False)
    note = Column(Text, nullable=True)            # personal note from student
    bookmarked_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("StudentProfile", back_populates="bookmarks")
    question = relationship("Question", back_populates="bookmarks")


class GenerationJob(Base):
    """Tracks async quiz generation jobs."""
    __tablename__ = "generation_jobs"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=True)
    topic = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)
    status = Column(String, default="queued")   # queued | running | done | failed
    questions_generated = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CheatSession(Base):
    """Tracks a student's quiz session for integrity monitoring."""
    __tablename__ = "cheat_sessions"

    id = Column(String, primary_key=True, default=gen_id)
    student_id = Column(String, ForeignKey("student_profiles.student_id"), nullable=False)
    session_token = Column(String, unique=True, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    risk_score = Column(Integer, default=0)
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(Text, nullable=True)

    events = relationship("CheatEvent", back_populates="session", cascade="all, delete")


class CheatEvent(Base):
    """Individual cheat signal events recorded from the frontend during a session."""
    __tablename__ = "cheat_events"

    id = Column(String, primary_key=True, default=gen_id)
    session_id = Column(String, ForeignKey("cheat_sessions.id"), nullable=False)
    # tab_switch | focus_loss | copy_paste | fast_submit | right_click | devtools_open | idle_then_fast
    event_type = Column(String, nullable=False)
    question_id = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("CheatSession", back_populates="events")
