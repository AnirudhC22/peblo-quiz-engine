"""
Full test suite for Peblo AI Quiz Engine.

Tests are grouped by module:
  - TestHealth          : root and health endpoints
  - TestIngestion       : document listing (no real PDF in CI)
  - TestQuizRetrieval   : GET /quiz with filters
  - TestAnswerSubmission: submit-answer flow + adaptive difficulty
  - TestStudentDashboard: dashboard, bookmarks, weak-areas
  - TestIntegrityMonitor: full cheat-session lifecycle
  - TestAdaptiveEngine  : unit tests for difficulty algorithm
  - TestCheatDetection  : unit tests for risk scoring
  - TestQuizGenerator   : unit tests for validation & dedup logic
"""

import pytest


# ============================================================
# Health
# ============================================================

class TestHealth:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "running"
        assert body["service"] == "Peblo AI Quiz Engine"

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


# ============================================================
# Documents / Ingestion
# ============================================================

class TestIngestion:
    def test_list_documents_empty(self, client):
        r = client.get("/api/v1/documents")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_ingest_non_pdf_rejected(self, client):
        """Non-PDF uploads should return 400."""
        from io import BytesIO
        r = client.post(
            "/api/v1/ingest",
            files={"file": ("notes.txt", BytesIO(b"hello world"), "text/plain")},
        )
        assert r.status_code == 400
        assert "PDF" in r.json()["detail"]

    def test_document_chunks_not_found(self, client):
        r = client.get("/api/v1/documents/nonexistent-id/chunks")
        assert r.status_code == 404


# ============================================================
# Quiz Retrieval
# ============================================================

class TestQuizRetrieval:
    def test_quiz_empty_db(self, client):
        r = client.get("/api/v1/quiz")
        assert r.status_code == 200
        body = r.json()
        assert "questions" in body
        assert "total" in body
        assert "difficulty_used" in body
        assert isinstance(body["questions"], list)

    def test_quiz_with_topic_filter(self, client):
        r = client.get("/api/v1/quiz?topic=shapes&difficulty=easy")
        assert r.status_code == 200

    def test_quiz_with_all_filters(self, client):
        r = client.get(
            "/api/v1/quiz"
            "?subject=Math&grade=1&difficulty=easy"
            "&question_types=MCQ,TrueFalse&num_questions=5"
        )
        assert r.status_code == 200

    def test_quiz_num_questions_clamped(self, client):
        """num_questions > 50 should be rejected by Pydantic."""
        r = client.get("/api/v1/quiz?num_questions=999")
        assert r.status_code == 422

    def test_quiz_adaptive_no_student(self, client):
        """difficulty=auto with no student_id defaults to easy."""
        r = client.get("/api/v1/quiz?difficulty=auto")
        assert r.status_code == 200
        assert r.json()["difficulty_used"] == "easy"

    def test_hint_question_not_found(self, client):
        r = client.get("/api/v1/quiz/nonexistent-question-id/hint")
        assert r.status_code == 404

    def test_question_stats(self, client):
        r = client.get("/api/v1/questions/stats")
        assert r.status_code == 200
        body = r.json()
        assert "total_questions" in body
        assert "by_difficulty" in body
        assert "by_type" in body
        assert "by_subject" in body

    def test_job_not_found(self, client):
        r = client.get("/api/v1/jobs/nonexistent-job-id")
        assert r.status_code == 404


# ============================================================
# Answer Submission + Adaptive Difficulty
# ============================================================

class TestAnswerSubmission:
    def _seed_question(self, db):
        """Insert a real question directly into the test DB."""
        import uuid, json
        from app.models.database_models import Document, Chunk, Question

        doc = Document(
            id=str(uuid.uuid4()),
            file_name="test.pdf",
            subject="Math",
            grade=1,
            status="processed",
        )
        db.add(doc)
        db.flush()

        chunk = Chunk(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            chunk_index=0,
            topic="Shapes",
            text="A triangle has three sides.",
            word_count=6,
        )
        db.add(chunk)
        db.flush()

        q = Question(
            id=str(uuid.uuid4()),
            chunk_id=chunk.id,
            question="How many sides does a triangle have?",
            question_type="MCQ",
            options_json=json.dumps(["2", "3", "4", "5"]),
            answer="3",
            difficulty="easy",
            topic="Shapes",
            subject="Math",
            grade=1,
        )
        db.add(q)
        db.commit()
        return q.id

    def test_submit_correct_answer(self, client, db):
        qid = self._seed_question(db)
        r = client.post("/api/v1/submit-answer", json={
            "student_id": "STUDENT_TEST_CORRECT",
            "question_id": qid,
            "selected_answer": "3",
            "time_taken_seconds": 10,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["is_correct"] is True
        assert body["correct_answer"] == "3"
        assert body["streak"] == 1
        assert body["accuracy"] == 100.0

    def test_submit_wrong_answer(self, client, db):
        qid = self._seed_question(db)
        r = client.post("/api/v1/submit-answer", json={
            "student_id": "STUDENT_TEST_WRONG",
            "question_id": qid,
            "selected_answer": "4",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["is_correct"] is False
        assert body["streak"] == 0

    def test_submit_case_insensitive(self, client, db):
        """Answers should match regardless of case."""
        import uuid, json
        from app.models.database_models import Document, Chunk, Question
        doc = Document(id=str(uuid.uuid4()), file_name="t.pdf", subject="Science", grade=3, status="processed")
        db.add(doc)
        db.flush()
        chunk = Chunk(id=str(uuid.uuid4()), document_id=doc.id, chunk_index=0, text="Plants need sunlight.", word_count=4)
        db.add(chunk)
        db.flush()
        q = Question(
            id=str(uuid.uuid4()), chunk_id=chunk.id,
            question="A triangle has three sides.",
            question_type="TrueFalse",
            options_json=json.dumps(["True", "False"]),
            answer="True", difficulty="easy",
        )
        db.add(q)
        db.commit()

        r = client.post("/api/v1/submit-answer", json={
            "student_id": "CASE_STUDENT",
            "question_id": q.id,
            "selected_answer": "true",   # lowercase
        })
        assert r.status_code == 200
        assert r.json()["is_correct"] is True

    def test_submit_question_not_found(self, client):
        r = client.post("/api/v1/submit-answer", json={
            "student_id": "S001",
            "question_id": "bad-id",
            "selected_answer": "x",
        })
        assert r.status_code == 404

    def test_streak_fast_track_promotion(self, client, db):
        """3 correct in a row should trigger difficulty promotion."""
        import uuid, json
        from app.models.database_models import Document, Chunk, Question

        doc = Document(id=str(uuid.uuid4()), file_name="s.pdf", subject="Math", grade=1, status="processed")
        db.add(doc)
        db.flush()
        chunk = Chunk(id=str(uuid.uuid4()), document_id=doc.id, chunk_index=0, text="Numbers.", word_count=1)
        db.add(chunk)
        db.flush()

        # Create 3 questions with known answers: "2", "3", "4"
        q_ids = []
        for i in range(3):
            q = Question(
                id=str(uuid.uuid4()), chunk_id=chunk.id,
                question=f"Streak test question {i}: what is {i+1}+1?",
                question_type="MCQ",
                options_json=json.dumps([str(i+1), str(i+2), str(i+3), str(i+4)]),
                answer=str(i+2), difficulty="easy",
            )
            db.add(q)
            q_ids.append((q.id, str(i+2)))  # (id, correct_answer)
        db.commit()

        sid = "STREAK_STUDENT_CLEAN"
        for qid, correct_ans in q_ids:
            r = client.post("/api/v1/submit-answer", json={
                "student_id": sid,
                "question_id": qid,
                "selected_answer": correct_ans,
            })
            assert r.status_code == 200

        last = r.json()
        assert last["streak"] == 3
        # After 3 correct easy answers → should promote to medium
        assert last["new_difficulty"] == "medium"


# ============================================================
# Student Dashboard
# ============================================================

class TestStudentDashboard:
    def test_dashboard_not_found(self, client):
        r = client.get("/api/v1/students/GHOST_999/dashboard")
        assert r.status_code == 404

    def test_dashboard_after_answer(self, client, db):
        """Dashboard should appear after student submits at least one answer."""
        import uuid, json
        from app.models.database_models import Document, Chunk, Question

        doc = Document(id=str(uuid.uuid4()), file_name="d.pdf", subject="English", grade=4, status="processed")
        db.add(doc)
        db.flush()
        chunk = Chunk(id=str(uuid.uuid4()), document_id=doc.id, chunk_index=0, text="Grammar rules.", word_count=2)
        db.add(chunk)
        db.flush()
        q = Question(
            id=str(uuid.uuid4()), chunk_id=chunk.id,
            question="A noun names a person, place, or ___.",
            question_type="FillBlank",
            options_json=json.dumps([]),
            answer="thing", difficulty="easy",
        )
        db.add(q)
        db.commit()

        sid = "DASHBOARD_STUDENT"
        client.post("/api/v1/submit-answer", json={
            "student_id": sid, "question_id": q.id, "selected_answer": "thing"
        })

        r = client.get(f"/api/v1/students/{sid}/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert body["student_id"] == sid
        assert body["total_attempted"] == 1
        assert body["total_correct"] == 1
        assert body["accuracy"] == 100.0
        assert body["streak_current"] == 1
        assert "subject_breakdown" in body
        assert "recent_performance" in body

    def test_weak_areas_empty(self, client):
        r = client.get("/api/v1/students/NEW_STUDENT_NODATA/weak-areas")
        assert r.status_code == 200
        assert r.json()["weak_areas"] == []

    def test_bookmark_flow(self, client, db):
        """Full bookmark add → list → remove cycle."""
        import uuid, json
        from app.models.database_models import Document, Chunk, Question

        doc = Document(id=str(uuid.uuid4()), file_name="bm.pdf", subject="Math", grade=1, status="processed")
        db.add(doc)
        db.flush()
        chunk = Chunk(id=str(uuid.uuid4()), document_id=doc.id, chunk_index=0, text="A circle is round.", word_count=4)
        db.add(chunk)
        db.flush()
        q = Question(
            id=str(uuid.uuid4()), chunk_id=chunk.id,
            question="What shape has no corners?",
            question_type="MCQ",
            options_json=json.dumps(["Square", "Triangle", "Circle", "Rectangle"]),
            answer="Circle", difficulty="easy",
        )
        db.add(q)
        db.commit()

        sid = "BOOKMARK_STUDENT"

        # Add bookmark with note
        r = client.post("/api/v1/bookmarks", json={
            "student_id": sid,
            "question_id": q.id,
            "note": "Need to review shapes",
        })
        assert r.status_code == 200
        assert r.json()["bookmarked"] is True

        # List bookmarks
        r2 = client.get(f"/api/v1/students/{sid}/bookmarks")
        assert r2.status_code == 200
        bms = r2.json()["bookmarks"]
        assert len(bms) == 1
        assert bms[0]["note"] == "Need to review shapes"
        assert bms[0]["question"]["id"] == q.id

        # Update note
        r3 = client.post("/api/v1/bookmarks", json={
            "student_id": sid, "question_id": q.id, "note": "Reviewed!"
        })
        assert r3.json()["message"] == "Bookmark updated."

        # Remove bookmark
        r4 = client.delete(f"/api/v1/bookmarks?student_id={sid}&question_id={q.id}")
        assert r4.status_code == 200
        assert r4.json()["bookmarked"] is False

        # Confirm removed
        r5 = client.get(f"/api/v1/students/{sid}/bookmarks")
        assert r5.json()["total"] == 0

    def test_bookmark_question_not_found(self, client):
        r = client.post("/api/v1/bookmarks", json={
            "student_id": "S001", "question_id": "bad-id"
        })
        assert r.status_code == 404


# ============================================================
# Academic Integrity Monitor
# ============================================================

class TestIntegrityMonitor:
    def test_start_session(self, client):
        r = client.post("/api/v1/sessions/start", json={"student_id": "MON_S001"})
        assert r.status_code == 200
        body = r.json()
        assert "session_token" in body
        assert body["student_id"] == "MON_S001"

    def test_record_tab_switch(self, client):
        r = client.post("/api/v1/sessions/start", json={"student_id": "MON_S002"})
        token = r.json()["session_token"]

        r2 = client.post(f"/api/v1/sessions/{token}/event", json={
            "event_type": "tab_switch",
            "detail": "Switched to Google",
        })
        assert r2.status_code == 200
        body = r2.json()
        assert body["recorded"] is True
        assert body["current_risk_score"] == 15   # tab_switch weight

    def test_invalid_event_type(self, client):
        r = client.post("/api/v1/sessions/start", json={"student_id": "MON_S003"})
        token = r.json()["session_token"]

        r2 = client.post(f"/api/v1/sessions/{token}/event", json={
            "event_type": "INVALID_EVENT",
        })
        assert r2.status_code == 400

    def test_session_not_found(self, client):
        r = client.post("/api/v1/sessions/bad-token/event", json={
            "event_type": "tab_switch"
        })
        assert r.status_code == 404

    def test_end_session_clean(self, client):
        r = client.post("/api/v1/sessions/start", json={"student_id": "MON_CLEAN"})
        token = r.json()["session_token"]

        r2 = client.post(f"/api/v1/sessions/{token}/end")
        assert r2.status_code == 200
        body = r2.json()
        assert body["risk_score"] == 0
        assert body["is_flagged"] is False
        assert body["total_events"] == 0

    def test_end_session_flagged(self, client):
        """devtools(30) + copy_paste(20) + fast_submit(25) = 75 → flagged."""
        r = client.post("/api/v1/sessions/start", json={"student_id": "MON_CHEAT"})
        token = r.json()["session_token"]

        for ev in ["devtools_open", "copy_paste", "fast_submit"]:
            client.post(f"/api/v1/sessions/{token}/event", json={"event_type": ev})

        r_end = client.post(f"/api/v1/sessions/{token}/end")
        body = r_end.json()
        assert body["is_flagged"] is True
        assert body["risk_score"] >= 50
        assert body["flag_reason"] is not None

    def test_full_report(self, client):
        r = client.post("/api/v1/sessions/start", json={"student_id": "MON_REPORT"})
        token = r.json()["session_token"]

        client.post(f"/api/v1/sessions/{token}/event", json={
            "event_type": "focus_loss", "detail": "alt-tabbed"
        })
        client.post(f"/api/v1/sessions/{token}/end")

        r2 = client.get(f"/api/v1/sessions/{token}/report")
        assert r2.status_code == 200
        body = r2.json()
        assert body["session_token"] == token
        assert len(body["events"]) == 1
        assert body["events"][0]["event_type"] == "focus_loss"
        assert body["events"][0]["risk_weight"] == 10
        assert "risk_level" in body

    def test_event_after_session_ended(self, client):
        """Cannot record events after session ends."""
        r = client.post("/api/v1/sessions/start", json={"student_id": "MON_ENDED"})
        token = r.json()["session_token"]
        client.post(f"/api/v1/sessions/{token}/end")

        r2 = client.post(f"/api/v1/sessions/{token}/event", json={"event_type": "tab_switch"})
        assert r2.status_code == 400

    def test_student_integrity_overview(self, client):
        sid = "MON_OVERVIEW"
        r = client.post("/api/v1/sessions/start", json={"student_id": sid})
        token = r.json()["session_token"]
        client.post(f"/api/v1/sessions/{token}/end")

        r2 = client.get(f"/api/v1/students/{sid}/integrity")
        assert r2.status_code == 200
        body = r2.json()
        assert body["total_sessions"] == 1
        assert body["flagged_sessions"] == 0

    def test_risk_score_accumulates(self, client):
        """Multiple events of same type should stack."""
        r = client.post("/api/v1/sessions/start", json={"student_id": "MON_STACK"})
        token = r.json()["session_token"]

        # 3 tab switches = 3 × 15 = 45
        for _ in range(3):
            r2 = client.post(f"/api/v1/sessions/{token}/event", json={"event_type": "tab_switch"})

        assert r2.json()["current_risk_score"] == 45
        assert r2.json()["flagged"] is False  # 45 < 50


# ============================================================
# Unit: Adaptive Engine
# ============================================================

class TestAdaptiveEngine:
    def test_promote_on_high_accuracy(self):
        from app.services.adaptive_engine import get_next_difficulty
        answers = [True] * 9 + [False]   # 90% accuracy
        diff, msg = get_next_difficulty("easy", answers)
        assert diff == "medium"
        assert "medium" in msg

    def test_demote_on_low_accuracy(self):
        from app.services.adaptive_engine import get_next_difficulty
        answers = [False] * 8 + [True] * 2   # 20% accuracy
        diff, msg = get_next_difficulty("medium", answers)
        assert diff == "easy"

    def test_stay_on_medium_accuracy(self):
        from app.services.adaptive_engine import get_next_difficulty
        answers = [True, False] * 5   # 50% accuracy
        diff, msg = get_next_difficulty("medium", answers)
        assert diff == "medium"

    def test_no_promote_past_hard(self):
        from app.services.adaptive_engine import get_next_difficulty
        answers = [True] * 10
        diff, _ = get_next_difficulty("hard", answers)
        assert diff == "hard"

    def test_no_demote_below_easy(self):
        from app.services.adaptive_engine import get_next_difficulty
        answers = [False] * 10
        diff, _ = get_next_difficulty("easy", answers)
        assert diff == "easy"

    def test_streak_fast_track(self):
        from app.services.adaptive_engine import get_next_difficulty
        diff, msg = get_next_difficulty("easy", [], streak_correct=3)
        assert diff == "medium"
        assert "🔥" in msg

    def test_streak_reset_on_wrong(self):
        from app.services.adaptive_engine import update_streak
        streak, _ = update_streak(5, False)
        assert streak == 0

    def test_streak_increment_on_correct(self):
        from app.services.adaptive_engine import update_streak
        streak, best = update_streak(2, True)
        assert streak == 3
        assert best == 3

    def test_empty_answers_no_change(self):
        from app.services.adaptive_engine import get_next_difficulty
        diff, msg = get_next_difficulty("medium", [])
        assert diff == "medium"

    def test_suggest_difficulty(self):
        from app.services.adaptive_engine import suggest_next_question_difficulty
        assert suggest_next_question_difficulty(85.0, "easy") == "medium"
        assert suggest_next_question_difficulty(30.0, "medium") == "easy"
        assert suggest_next_question_difficulty(60.0, "medium") == "medium"


# ============================================================
# Unit: Cheat Detection Risk Scoring
# ============================================================

class TestCheatDetection:
    def test_empty_events_zero_score(self):
        from app.services.cheat_detection import compute_risk_score
        assert compute_risk_score([]) == 0

    def test_tab_switch_score(self):
        from app.services.cheat_detection import compute_risk_score
        assert compute_risk_score([{"event_type": "tab_switch"}]) == 15

    def test_devtools_score(self):
        from app.services.cheat_detection import compute_risk_score
        assert compute_risk_score([{"event_type": "devtools_open"}]) == 30

    def test_score_capped_at_100(self):
        from app.services.cheat_detection import compute_risk_score
        events = [{"event_type": "devtools_open"}] * 10
        assert compute_risk_score(events) == 100

    def test_fast_submit_detection(self):
        from app.services.cheat_detection import is_fast_submit
        assert is_fast_submit(1, "What is the capital of France?") is True
        assert is_fast_submit(30, "What is the capital of France?") is False
        assert is_fast_submit(None, "Anything") is False

    def test_combined_events(self):
        from app.services.cheat_detection import compute_risk_score, FLAG_THRESHOLD
        events = [
            {"event_type": "tab_switch"},       # 15
            {"event_type": "copy_paste"},        # 20
            {"event_type": "devtools_open"},     # 30
        ]
        score = compute_risk_score(events)
        assert score == 65
        assert score >= FLAG_THRESHOLD


# ============================================================
# Unit: Quiz Generator (validation & dedup — no LLM calls)
# ============================================================

class TestQuizGeneratorValidation:
    def test_valid_mcq(self):
        from app.services.quiz_generator import _validate_question
        q = {
            "question": "How many sides does a triangle have?",
            "type": "MCQ",
            "options": ["2", "3", "4", "5"],
            "answer": "3",
            "difficulty": "easy",
        }
        valid, score = _validate_question(q)
        assert valid is True
        assert score == 1.0

    def test_invalid_mcq_answer_not_in_options(self):
        from app.services.quiz_generator import _validate_question
        q = {
            "question": "What color is the sky?",
            "type": "MCQ",
            "options": ["Red", "Green", "Yellow", "Purple"],
            "answer": "Blue",
            "difficulty": "easy",
        }
        valid, _ = _validate_question(q)
        assert valid is False

    def test_invalid_mcq_wrong_option_count(self):
        from app.services.quiz_generator import _validate_question
        q = {
            "question": "Pick one?",
            "type": "MCQ",
            "options": ["A", "B"],   # only 2, need 4
            "answer": "A",
            "difficulty": "easy",
        }
        valid, _ = _validate_question(q)
        assert valid is False

    def test_valid_truefalse(self):
        from app.services.quiz_generator import _validate_question
        q = {
            "question": "A triangle has three sides.",
            "type": "TrueFalse",
            "options": ["True", "False"],
            "answer": "True",
            "difficulty": "medium",
        }
        valid, score = _validate_question(q)
        assert valid is True

    def test_invalid_truefalse_bad_answer(self):
        from app.services.quiz_generator import _validate_question
        q = {
            "question": "Something is true.",
            "type": "TrueFalse",
            "options": ["True", "False"],
            "answer": "Maybe",
            "difficulty": "easy",
        }
        valid, _ = _validate_question(q)
        assert valid is False

    def test_valid_fillblank(self):
        from app.services.quiz_generator import _validate_question
        q = {
            "question": "A ___ has four sides.",
            "type": "FillBlank",
            "options": [],
            "answer": "square",
            "difficulty": "hard",
        }
        valid, _ = _validate_question(q)
        assert valid is True

    def test_invalid_difficulty(self):
        from app.services.quiz_generator import _validate_question
        q = {
            "question": "Test?",
            "type": "MCQ",
            "options": ["A", "B", "C", "D"],
            "answer": "A",
            "difficulty": "superhard",   # invalid
        }
        valid, _ = _validate_question(q)
        assert valid is False

    def test_missing_required_fields(self):
        from app.services.quiz_generator import _validate_question
        valid, _ = _validate_question({"question": "Incomplete"})
        assert valid is False

    def test_deduplication_removes_similar(self):
        from app.services.quiz_generator import deduplicate_questions
        existing = ["How many sides does a triangle have?"]
        new_qs = [
            {
                "question": "How many sides does a triangle have?",
                "type": "MCQ", "answer": "3", "difficulty": "easy"
            },
            {
                "question": "What is the capital of France?",
                "type": "MCQ", "answer": "Paris", "difficulty": "medium"
            },
        ]
        result = deduplicate_questions(new_qs, existing, threshold=0.85)
        assert len(result) == 1
        assert result[0]["answer"] == "Paris"

    def test_deduplication_keeps_distinct(self):
        from app.services.quiz_generator import deduplicate_questions
        existing = ["What color is grass?"]
        new_qs = [
            {"question": "How many legs does a spider have?", "type": "MCQ", "answer": "8", "difficulty": "easy"},
            {"question": "What is the boiling point of water?", "type": "MCQ", "answer": "100", "difficulty": "medium"},
        ]
        result = deduplicate_questions(new_qs, existing)
        assert len(result) == 2

    def test_cosine_similarity_identical(self):
        from app.services.quiz_generator import _cosine_similarity, _word_vector
        a = _word_vector("the cat sat on the mat")
        b = _word_vector("the cat sat on the mat")
        assert _cosine_similarity(a, b) == pytest.approx(1.0)

    def test_cosine_similarity_different(self):
        from app.services.quiz_generator import _cosine_similarity, _word_vector
        a = _word_vector("triangle has three sides")
        b = _word_vector("photosynthesis requires sunlight water carbon dioxide")
        sim = _cosine_similarity(a, b)
        assert sim < 0.2


# ============================================================
# Unit: PDF Parser (text cleaning & chunking)
# ============================================================

class TestPDFParser:
    def test_clean_removes_page_numbers(self):
        from app.services.pdf_parser import _clean_text
        text = "A triangle has three sides.\n\nPage 3\n\nA square has four sides."
        cleaned = _clean_text(text)
        assert "Page 3" not in cleaned
        assert "triangle" in cleaned
        assert "square" in cleaned

    def test_clean_removes_standalone_numbers(self):
        from app.services.pdf_parser import _clean_text
        text = "Introduction\n\n3\n\nContent here."
        cleaned = _clean_text(text)
        assert cleaned.count("\n3\n") == 0

    def test_clean_normalizes_whitespace(self):
        from app.services.pdf_parser import _clean_text
        text = "Hello   world   with  spaces"
        cleaned = _clean_text(text)
        assert "  " not in cleaned

    def test_infer_metadata_math(self):
        from app.services.pdf_parser import _infer_metadata
        subject, grade = _infer_metadata("peblo_pdf_grade1_math_numbers.pdf")
        assert subject == "Math"
        assert grade == 1

    def test_infer_metadata_english(self):
        from app.services.pdf_parser import _infer_metadata
        subject, grade = _infer_metadata("peblo_pdf_grade4_english_grammar.pdf")
        assert subject == "English"
        assert grade == 4

    def test_infer_metadata_science(self):
        from app.services.pdf_parser import _infer_metadata
        subject, grade = _infer_metadata("peblo_pdf_grade3_science_plants_animals.pdf")
        assert subject == "Science"
        assert grade == 3

    def test_semantic_chunking_respects_size(self):
        from app.services.pdf_parser import _semantic_chunk
        pages = [
            "A triangle has three sides. It is a polygon.\n\n"
            "A square has four equal sides. All angles are right angles.\n\n"
            "A circle has no corners. Its boundary is called a circumference.\n\n"
            "A rectangle has two pairs of equal sides. Opposite sides are parallel.",
        ]
        chunks = _semantic_chunk(pages, chunk_size=20)
        assert len(chunks) > 1
        for c in chunks:
            assert c.word_count >= 1

    def test_detect_topic_allcaps(self):
        from app.services.pdf_parser import _detect_topic
        text = "SHAPES AND GEOMETRY\n\nA triangle has three sides."
        topic = _detect_topic(text)
        assert topic is not None

    def test_chunk_filters_noise(self):
        from app.services.pdf_parser import _semantic_chunk
        # Single-word pages should be filtered out (word_count < 20)
        pages = ["3", "4", "5", "This is actual educational content about triangles having three sides and being a polygon with corners."]
        chunks = _semantic_chunk(pages, chunk_size=100)
        for c in chunks:
            assert c.word_count >= 20
