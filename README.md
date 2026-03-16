# 🎓 Peblo AI Quiz Engine

An AI-powered educational content ingestion and adaptive quiz platform built with **FastAPI**, **SQLite**, and **Gemini 2.5 Flash** (free tier).

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Client / Frontend                    │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│              FastAPI Application Layer                  │
│  RateLimitMiddleware  RequestLoggingMiddleware  CORS    │
│                                                         │
│  /ingest  /generate-quiz  /quiz  /submit-answer         │
│  /documents  /jobs  /students  /bookmarks  /sessions    │
└────────────────────────┬────────────────────────────────┘
          ┌──────────────┴──────────────┐
          │                             │
┌─────────▼──────────┐      ┌──────────▼──────────┐
│   Service Layer     │      │   SQLite Database   │
│  pdf_parser.py      │      │  documents          │
│  llm_client.py      │      │  chunks             │
│  quiz_generator.py  │      │  questions          │
│  adaptive_engine.py │      │  student_profiles   │
│  cheat_detection.py │      │  student_answers    │
└─────────┬───────────┘      │  bookmarks          │
          │                  │  cheat_sessions     │
┌─────────▼──────────┐      │  cheat_events       │
│  Gemini 2.5 Flash  │      │  generation_jobs    │
│  (Free Tier API)   │      └─────────────────────┘
└────────────────────┘
```

### Request Flow
```
POST /ingest        →  PDF → PyMuPDF → clean → chunk → DB
POST /generate-quiz →  chunks → Gemini 2.5 Flash → validate → dedup → DB (background)
GET  /quiz          →  filter by topic/subject/grade/difficulty/student → adaptive sort
POST /submit-answer →  check answer → update streak → adaptive engine → new difficulty
POST /sessions/start     → create session token
POST /sessions/{t}/event → record cheat signal → live risk score
POST /sessions/{t}/end   → final score, flag if >= 50
```

---

## ✨ Features

### Core Pipeline
| Feature | Detail |
|---|---|
| PDF Ingestion | PyMuPDF + pdfplumber fallback |
| Smart Chunking | Paragraph-boundary semantic chunking, not fixed word count |
| Text Cleaning | Removes page numbers, headers, dashes, normalizes whitespace |
| LLM Quiz Gen | Gemini 2.5 Flash — MCQ, True/False, Fill-in-blank |
| Source Traceability | Question → Chunk → Document full lineage |
| Duplicate Detection | Cosine similarity (word vectors), threshold 0.85 |
| Question Validation | Answer-in-options, option count, difficulty, quality score |
| Async Generation | BackgroundTasks — job_id returned immediately |

### Student Features
| Feature | Endpoint |
|---|---|
| Quiz Customizer | GET /quiz with 9 filter params |
| Adaptive Difficulty | Rolling 10-answer window, auto easy/medium/hard |
| Streak System | Current + best streak, fast-track at 3 correct in a row |
| AI Hints | GET /quiz/{id}/hint — Gemini hints without revealing answer |
| Learning Dashboard | Accuracy, streaks, subject breakdown, recent answers |
| Bookmarks | Add/update/remove with personal notes |
| Bookmarked Quiz | GET /quiz?bookmarked_only=true |
| Skip Attempted | GET /quiz?exclude_attempted=true |
| Weak Area Detection | Topics where accuracy < 60% |

### Academic Integrity Monitor
| Signal | Risk Weight | Detection Method |
|---|---|---|
| Tab switch | 15 | visibilitychange event |
| Window focus loss | 10 | window blur event |
| Copy-paste | 20 | document copy event |
| Answer too fast | 25 | time < min read time |
| Right-click | 5 | contextmenu event |
| DevTools open | 30 | outerHeight - innerHeight > 200 |
| Idle then fast | 20 | manual time tracking |

Flag threshold: **50 pts**. Drop-in JS: `app/utils/integrity_monitor.js`

---

## 📁 Project Structure

```
peblo-quiz-engine/
├── app/
│   ├── main.py                  FastAPI app entry point
│   ├── middleware.py             Rate limiting + request logging
│   ├── api/
│   │   ├── ingest_routes.py     POST /ingest, GET /documents
│   │   ├── quiz_routes.py       POST /generate-quiz, GET /quiz, hints
│   │   ├── student_routes.py    submit-answer, dashboard, bookmarks
│   │   └── monitor_routes.py    Cheat detection sessions
│   ├── services/
│   │   ├── pdf_parser.py        PDF → clean text → semantic chunks
│   │   ├── llm_client.py        Unified Gemini/OpenAI/Anthropic client
│   │   ├── quiz_generator.py    Prompts, validation, deduplication
│   │   ├── adaptive_engine.py   Difficulty algorithm
│   │   └── cheat_detection.py   Risk scoring
│   ├── models/
│   │   ├── database_models.py   SQLAlchemy ORM (8 tables)
│   │   └── schemas.py           Pydantic request/response models
│   ├── database/
│   │   └── db.py                Engine, sessions, init_db
│   └── utils/
│       └── integrity_monitor.js Drop-in frontend cheat monitor
├── tests/
│   ├── conftest.py              In-memory SQLite test DB + fixtures
│   ├── test_api.py              Smoke tests
│   └── test_full.py             50 tests across all modules
├── seed.py                      Demo data seeder (no PDF/LLM needed)
├── run.sh                       One-command startup with env checks
├── Makefile                     make setup/run/seed/test/clean
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── requirements.txt
├── .env.example
└── README.md
```

---

## ⚡ Quick Start

### Option A — Shell (recommended)
```bash
git clone <your-repo-url> && cd peblo-quiz-engine
cp .env.example .env
# Edit .env — add GEMINI_API_KEY (free at aistudio.google.com/app/apikey)
bash run.sh
```

### Option B — Make
```bash
make setup   # venv + deps + .env
# Edit .env
make seed    # optional demo data
make run
```

### Option C — Docker
```bash
cp .env.example .env  # add GEMINI_API_KEY
docker-compose up --build
```

Docs: **http://localhost:8000/docs**

---

## 🔌 API Reference

### Ingestion
```bash
curl -X POST http://localhost:8000/api/v1/ingest -F "file=@grades.pdf"
GET  /api/v1/documents
GET  /api/v1/documents/{id}/chunks?limit=5
```

### Quiz Generation
```bash
curl -X POST http://localhost:8000/api/v1/generate-quiz \
  -H "Content-Type: application/json" \
  -d '{"document_id":"uuid","difficulty":"easy","questions_per_chunk":3}'

GET /api/v1/jobs/{job_id}   # poll until status=done
```

### Quiz Retrieval
```bash
GET /api/v1/quiz?topic=shapes&difficulty=easy
GET /api/v1/quiz?student_id=S001&difficulty=auto&exclude_attempted=true
GET /api/v1/quiz?student_id=S001&bookmarked_only=true
GET /api/v1/quiz?subject=Math&grade=1&question_types=MCQ,FillBlank&num_questions=5
GET /api/v1/quiz/{question_id}/hint
GET /api/v1/questions/stats
```

### Answer Submission
```bash
curl -X POST http://localhost:8000/api/v1/submit-answer \
  -H "Content-Type: application/json" \
  -d '{"student_id":"S001","question_id":"uuid","selected_answer":"3","time_taken_seconds":12}'

# Response includes: is_correct, new_difficulty, streak, accuracy, difficulty_message
```

### Student Dashboard
```bash
GET  /api/v1/students/S001/dashboard
GET  /api/v1/students/S001/weak-areas
GET  /api/v1/students/S001/bookmarks
POST /api/v1/bookmarks           {"student_id":"S001","question_id":"uuid","note":"Review this"}
DELETE /api/v1/bookmarks?student_id=S001&question_id=uuid
```

### Integrity Monitor
```bash
# Start session
POST /api/v1/sessions/start  {"student_id":"S001"}

# Report events (called automatically by integrity_monitor.js)
POST /api/v1/sessions/{token}/event  {"event_type":"tab_switch"}
# → {"current_risk_score":15,"flagged":false}

# End session
POST /api/v1/sessions/{token}/end
# → {"risk_score":75,"is_flagged":true,"flag_reason":"..."}

GET /api/v1/sessions/{token}/report
GET /api/v1/students/S001/integrity
```

**Frontend setup:**
```javascript
// Include app/utils/integrity_monitor.js then:
const { session_token } = await fetch('/api/v1/sessions/start', {
  method: 'POST', headers: {'Content-Type':'application/json'},
  body: JSON.stringify({ student_id: 'S001' })
}).then(r => r.json());

const monitor = new PebloIntegrityMonitor({
  apiBase: 'http://localhost:8000/api/v1',
  sessionToken: session_token,
  onFlag: () => alert('⚠️ Suspicious activity detected'),
});
monitor.start();
monitor.setCurrentQuestion(questionId);  // call for each question
await monitor.checkSubmitSpeed();         // call before submitting
const report = await monitor.end();       // call when quiz ends
```

---

## 🗄 Database Schema (8 tables)

```
documents       → source PDFs (id, file_name, subject, grade, status)
  └─ chunks     → semantic segments (id, doc_id, chunk_index, topic, text)
       └─ questions → generated questions (id, chunk_id, type, answer, difficulty,
                       times_attempted, times_correct, quality_score)

student_profiles → (id, student_id, current_difficulty, streak_current, streak_best)
  └─ student_answers → (id, student_id, question_id, is_correct, time_taken_seconds)
  └─ bookmarks       → (id, student_id, question_id, note)
  └─ cheat_sessions  → (id, student_id, session_token, risk_score, is_flagged)
       └─ cheat_events → (id, session_id, event_type, detail, recorded_at)

generation_jobs → async job tracking (id, status, questions_generated)
```

---

## 🔁 Adaptive Difficulty

```
Rolling window: last 10 answers

accuracy >= 80%  →  promote to next level
accuracy <= 40%  →  demote to previous level
3 correct streak →  fast-track promote immediately  🔥

Levels: easy → medium → hard
```

---

## 🧪 Tests

```bash
make test                                          # all 50 tests
pytest tests/test_full.py -v -k TestIntegrityMonitor
pytest tests/test_full.py -v -k TestAdaptiveEngine
pytest tests/test_full.py -v -k TestCheatDetection
pytest tests/test_full.py -v -k TestPDFParser
```

---

## 🌍 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | No | `gemini` | gemini / openai / anthropic |
| `GEMINI_API_KEY` | **Yes** | — | Free at aistudio.google.com |
| `GEMINI_MODEL` | No | `gemini-2.5-flash-preview-04-17` | |
| `DATABASE_URL` | No | `sqlite:///./peblo_quiz.db` | SQLite or PostgreSQL URL |
| `UPLOAD_DIR` | No | `./uploads` | Temp PDF upload directory |

---

## 🚀 Demo Without a PDF

```bash
python seed.py          # creates 45 questions, 3 students, sample sessions
# or: make seed

curl "http://localhost:8000/api/v1/quiz?difficulty=easy&num_questions=5"
curl "http://localhost:8000/api/v1/students/S001/dashboard"
curl "http://localhost:8000/api/v1/questions/stats"
curl "http://localhost:8000/api/v1/students/S002/integrity"   # flagged session
```
