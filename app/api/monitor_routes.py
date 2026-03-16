"""
Cheat Monitor Routes
POST /sessions/start          — Start a monitored quiz session
POST /sessions/{token}/event  — Record a cheat signal event from frontend
POST /sessions/{token}/end    — End session, compute final risk score
GET  /sessions/{token}/report — Get full integrity report for a session
GET  /students/{id}/integrity — Overview of all sessions for a student
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.database_models import CheatEvent, CheatSession, StudentProfile
from app.services.cheat_detection import (
    FLAG_THRESHOLD,
    RISK_WEIGHTS,
    compute_risk_score,
    is_fast_submit,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas (defined inline to keep routes self-contained)
# ---------------------------------------------------------------------------

class StartSessionRequest(BaseModel):
    student_id: str


class StartSessionResponse(BaseModel):
    session_token: str
    student_id: str
    message: str


class CheatEventRequest(BaseModel):
    event_type: str           # tab_switch | focus_loss | copy_paste | fast_submit | right_click | devtools_open
    question_id: Optional[str] = None
    detail: Optional[str] = None


class EndSessionResponse(BaseModel):
    session_token: str
    risk_score: int
    is_flagged: bool
    flag_reason: Optional[str]
    total_events: int
    event_breakdown: dict


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/sessions/start", response_model=StartSessionResponse, summary="Start a monitored quiz session")
def start_session(req: StartSessionRequest, db: Session = Depends(get_db)):
    """
    Call this when a student starts a quiz.
    Returns a session_token that the frontend uses to report cheat events.
    """
    # Ensure student profile exists
    student = db.query(StudentProfile).filter(StudentProfile.student_id == req.student_id).first()
    if not student:
        # Auto-create
        student = StudentProfile(
            id=str(uuid.uuid4()),
            student_id=req.student_id,
        )
        db.add(student)
        db.flush()

    token = str(uuid.uuid4())
    session = CheatSession(
        id=str(uuid.uuid4()),
        student_id=req.student_id,
        session_token=token,
    )
    db.add(session)
    db.commit()

    logger.info(f"Started cheat-monitored session {token} for student {req.student_id}")
    return StartSessionResponse(
        session_token=token,
        student_id=req.student_id,
        message="Session started. All activity will be monitored for academic integrity.",
    )


@router.post("/sessions/{session_token}/event", summary="Record a cheat signal event")
def record_event(session_token: str, req: CheatEventRequest, db: Session = Depends(get_db)):
    """
    Called by the frontend JavaScript whenever a suspicious action is detected:
    - Tab switch (visibilitychange event)
    - Window blur / focus loss
    - Copy-paste on question text
    - Right-click attempt
    - DevTools open detection
    - Fast answer submission
    
    The backend accumulates these events and computes a live risk score.
    """
    session = db.query(CheatSession).filter(CheatSession.session_token == session_token).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session.ended_at:
        raise HTTPException(status_code=400, detail="Session already ended.")

    valid_types = set(RISK_WEIGHTS.keys())
    if req.event_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event_type. Valid types: {sorted(valid_types)}"
        )

    event = CheatEvent(
        id=str(uuid.uuid4()),
        session_id=session.id,
        event_type=req.event_type,
        question_id=req.question_id,
        detail=req.detail,
    )
    db.add(event)

    # Recompute live risk score
    all_events = db.query(CheatEvent).filter(CheatEvent.session_id == session.id).all()
    event_dicts = [{"event_type": e.event_type} for e in all_events]
    event_dicts.append({"event_type": req.event_type})
    session.risk_score = compute_risk_score(event_dicts)

    db.commit()

    logger.info(f"Session {session_token}: recorded '{req.event_type}' | risk_score={session.risk_score}")
    return {
        "recorded": True,
        "event_type": req.event_type,
        "current_risk_score": session.risk_score,
        "flagged": session.risk_score >= FLAG_THRESHOLD,
    }


@router.post("/sessions/{session_token}/end", response_model=EndSessionResponse, summary="End session and get integrity report")
def end_session(session_token: str, db: Session = Depends(get_db)):
    """
    Finalizes the session and computes the full integrity report.
    Call this when the student submits the quiz.
    """
    session = db.query(CheatSession).filter(CheatSession.session_token == session_token).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_events = db.query(CheatEvent).filter(CheatEvent.session_id == session.id).all()
    event_dicts = [{"event_type": e.event_type} for e in all_events]
    final_score = compute_risk_score(event_dicts)

    # Determine flag reason
    flag_reason = None
    if final_score >= FLAG_THRESHOLD:
        # Describe the top contributing events
        from collections import Counter
        counts = Counter(e.event_type for e in all_events)
        top = sorted(counts.items(), key=lambda x: RISK_WEIGHTS.get(x[0], 0) * x[1], reverse=True)
        reasons = [f"{t} ×{c}" for t, c in top[:3]]
        flag_reason = f"High-risk activity detected: {', '.join(reasons)}"

    session.ended_at = datetime.utcnow()
    session.risk_score = final_score
    session.is_flagged = final_score >= FLAG_THRESHOLD
    session.flag_reason = flag_reason
    db.commit()

    # Event breakdown
    from collections import Counter
    breakdown = dict(Counter(e.event_type for e in all_events))

    logger.info(
        f"Session {session_token} ended | risk={final_score} | flagged={session.is_flagged}"
    )

    return EndSessionResponse(
        session_token=session_token,
        risk_score=final_score,
        is_flagged=session.is_flagged,
        flag_reason=flag_reason,
        total_events=len(all_events),
        event_breakdown=breakdown,
    )


@router.get("/sessions/{session_token}/report", summary="Get detailed session integrity report")
def session_report(session_token: str, db: Session = Depends(get_db)):
    """Full audit report: all events with timestamps, risk score, flag status."""
    session = db.query(CheatSession).filter(CheatSession.session_token == session_token).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    events = (
        db.query(CheatEvent)
        .filter(CheatEvent.session_id == session.id)
        .order_by(CheatEvent.recorded_at)
        .all()
    )

    return {
        "session_token": session_token,
        "student_id": session.student_id,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "risk_score": session.risk_score,
        "is_flagged": session.is_flagged,
        "flag_reason": session.flag_reason,
        "risk_level": (
            "🟢 Low" if session.risk_score < 25
            else "🟡 Medium" if session.risk_score < FLAG_THRESHOLD
            else "🔴 High"
        ),
        "events": [
            {
                "event_type": e.event_type,
                "question_id": e.question_id,
                "detail": e.detail,
                "risk_weight": RISK_WEIGHTS.get(e.event_type, 0),
                "recorded_at": e.recorded_at,
            }
            for e in events
        ],
    }


@router.get("/students/{student_id}/integrity", summary="Student integrity overview across all sessions")
def student_integrity(student_id: str, db: Session = Depends(get_db)):
    """Shows all quiz sessions for a student with their risk scores — useful for educators."""
    sessions = (
        db.query(CheatSession)
        .filter(CheatSession.student_id == student_id)
        .order_by(CheatSession.started_at.desc())
        .all()
    )

    return {
        "student_id": student_id,
        "total_sessions": len(sessions),
        "flagged_sessions": sum(1 for s in sessions if s.is_flagged),
        "average_risk_score": round(sum(s.risk_score for s in sessions) / len(sessions), 1) if sessions else 0,
        "sessions": [
            {
                "session_token": s.session_token,
                "risk_score": s.risk_score,
                "is_flagged": s.is_flagged,
                "flag_reason": s.flag_reason,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
            }
            for s in sessions
        ],
    }
