"""
Basic API tests using FastAPI TestClient.
Run: pytest tests/ -v
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.db import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "running"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_list_documents_empty():
    r = client.get("/api/v1/documents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_quiz_empty():
    r = client.get("/api/v1/quiz")
    assert r.status_code == 200
    data = r.json()
    assert "questions" in data
    assert "total" in data


def test_submit_answer_question_not_found():
    r = client.post("/api/v1/submit-answer", json={
        "student_id": "TEST001",
        "question_id": "nonexistent-id",
        "selected_answer": "A",
    })
    assert r.status_code == 404


def test_student_dashboard_not_found():
    r = client.get("/api/v1/students/GHOST_STUDENT/dashboard")
    assert r.status_code == 404


def test_start_cheat_session():
    r = client.post("/api/v1/sessions/start", json={"student_id": "TEST_MONITOR"})
    assert r.status_code == 200
    data = r.json()
    assert "session_token" in data
    token = data["session_token"]

    # Record an event
    r2 = client.post(f"/api/v1/sessions/{token}/event", json={
        "event_type": "tab_switch",
        "detail": "Test tab switch",
    })
    assert r2.status_code == 200
    assert r2.json()["current_risk_score"] == 15  # tab_switch weight

    # End session
    r3 = client.post(f"/api/v1/sessions/{token}/end")
    assert r3.status_code == 200
    assert r3.json()["risk_score"] == 15
    assert r3.json()["is_flagged"] is False


def test_cheat_session_flag():
    r = client.post("/api/v1/sessions/start", json={"student_id": "CHEAT_STUDENT"})
    token = r.json()["session_token"]

    # Trigger enough events to exceed threshold (50)
    events = ["devtools_open", "copy_paste", "fast_submit"]
    for ev in events:
        client.post(f"/api/v1/sessions/{token}/event", json={"event_type": ev})

    r_end = client.post(f"/api/v1/sessions/{token}/end")
    data = r_end.json()
    # devtools(30) + copy_paste(20) + fast_submit(25) = 75 → flagged
    assert data["is_flagged"] is True
    assert data["risk_score"] >= 50


def test_question_stats():
    r = client.get("/api/v1/questions/stats")
    assert r.status_code == 200
    assert "total_questions" in r.json()
