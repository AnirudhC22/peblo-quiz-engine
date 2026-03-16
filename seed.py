"""
Demo Seed Script
────────────────
Populates the database with realistic sample data so you can demo
ALL endpoints immediately — no PDF upload or LLM call required.

Usage:
    python seed.py

What it creates:
    - 3 source documents (Math, English, Science)
    - 15 content chunks (5 per document)
    - 45 quiz questions (15 per document, mix of MCQ/TrueFalse/FillBlank)
    - 3 student profiles with answer history and bookmarks
    - 2 cheat monitoring sessions (1 clean, 1 flagged)
"""

import json
import os
import uuid
from datetime import datetime, timedelta
import random

# Load env
from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("DATABASE_URL", "sqlite:///./peblo_quiz.db")

from app.database.db import init_db, SessionLocal
from app.models.database_models import (
    Bookmark, Chunk, CheatEvent, CheatSession,
    Document, Question, StudentAnswer, StudentProfile,
)


# ── Sample data ──────────────────────────────────────────────────────────────

DOCUMENTS = [
    {
        "file_name": "peblo_pdf_grade1_math_numbers.pdf",
        "subject": "Math",
        "grade": 1,
        "chunks": [
            {"topic": "Counting", "text": "We count numbers from 1 to 10. One, two, three, four, five, six, seven, eight, nine, ten. Counting helps us know how many things we have."},
            {"topic": "Shapes", "text": "A triangle has three sides and three corners. A square has four equal sides. A circle is perfectly round and has no corners. A rectangle has two long sides and two short sides."},
            {"topic": "Addition", "text": "Adding means putting numbers together. When we add 2 and 3 we get 5. The plus sign (+) means add. The answer to an addition problem is called the sum."},
            {"topic": "Subtraction", "text": "Subtraction means taking away. When we take 2 away from 5 we get 3. The minus sign (-) means subtract. The answer to a subtraction problem is called the difference."},
            {"topic": "Patterns", "text": "A pattern repeats itself. Red, blue, red, blue is a pattern. Patterns can use colors, shapes, or numbers. Finding patterns helps us predict what comes next."},
        ],
    },
    {
        "file_name": "peblo_pdf_grade4_english_grammar.pdf",
        "subject": "English",
        "grade": 4,
        "chunks": [
            {"topic": "Nouns", "text": "A noun is a word that names a person, place, thing, or idea. Examples of nouns: teacher, school, book, happiness. Proper nouns name specific people or places and are capitalized."},
            {"topic": "Verbs", "text": "A verb is an action word. Verbs tell us what someone or something does. Examples: run, jump, think, eat. Every sentence must have a verb. Verbs can be in past, present, or future tense."},
            {"topic": "Adjectives", "text": "An adjective describes a noun. Adjectives tell us what kind, how many, or which one. Examples: tall, three, that. The tall girl carried three heavy books across the wide hallway."},
            {"topic": "Punctuation", "text": "A sentence always ends with a punctuation mark. A period ends a statement. A question mark ends a question. An exclamation mark shows strong feeling. Commas separate items in a list."},
            {"topic": "Sentences", "text": "A sentence is a complete thought. Every sentence has a subject and a predicate. The subject is who or what the sentence is about. The predicate tells what the subject does or is."},
        ],
    },
    {
        "file_name": "peblo_pdf_grade3_science_plants_animals.pdf",
        "subject": "Science",
        "grade": 3,
        "chunks": [
            {"topic": "Photosynthesis", "text": "Plants make their own food using sunlight, water, and carbon dioxide. This process is called photosynthesis. It happens in the green parts of the plant. Oxygen is released as a result of photosynthesis."},
            {"topic": "Plant Parts", "text": "A plant has roots, a stem, leaves, and flowers. Roots absorb water and nutrients from the soil. The stem carries water to the rest of the plant. Leaves capture sunlight to make food."},
            {"topic": "Animal Groups", "text": "Animals are grouped by their features. Mammals have fur and feed their babies milk. Birds have feathers and lay eggs. Fish live in water and breathe through gills. Reptiles have scales and are cold-blooded."},
            {"topic": "Food Chain", "text": "A food chain shows how energy moves through living things. Plants are producers because they make food. Animals that eat plants are called herbivores. Animals that eat other animals are called carnivores."},
            {"topic": "Habitats", "text": "A habitat is where a plant or animal lives. A desert habitat is hot and dry. An ocean habitat is saltwater. A forest habitat has many trees. Animals are adapted to survive in their habitats."},
        ],
    },
]

QUESTIONS_TEMPLATE = {
    "Math": [
        # Counting
        {"question": "What number comes after 9 when counting to 10?", "type": "MCQ", "options": ["7", "8", "10", "11"], "answer": "10", "difficulty": "easy", "topic": "Counting"},
        {"question": "We count numbers from 1 to 10.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Counting"},
        {"question": "Counting helps us know how many ___ we have.", "type": "FillBlank", "options": [], "answer": "things", "difficulty": "easy", "topic": "Counting"},
        # Shapes
        {"question": "How many sides does a triangle have?", "type": "MCQ", "options": ["2", "3", "4", "5"], "answer": "3", "difficulty": "easy", "topic": "Shapes"},
        {"question": "A circle has four corners.", "type": "TrueFalse", "options": ["True", "False"], "answer": "False", "difficulty": "easy", "topic": "Shapes"},
        {"question": "A square has ___ equal sides.", "type": "FillBlank", "options": [], "answer": "four", "difficulty": "easy", "topic": "Shapes"},
        # Addition
        {"question": "What is the answer to an addition problem called?", "type": "MCQ", "options": ["Difference", "Product", "Sum", "Quotient"], "answer": "Sum", "difficulty": "medium", "topic": "Addition"},
        {"question": "The plus sign means subtract.", "type": "TrueFalse", "options": ["True", "False"], "answer": "False", "difficulty": "easy", "topic": "Addition"},
        {"question": "When we add 2 and 3 we get ___.", "type": "FillBlank", "options": [], "answer": "5", "difficulty": "easy", "topic": "Addition"},
        # Subtraction
        {"question": "What is the answer to a subtraction problem called?", "type": "MCQ", "options": ["Sum", "Difference", "Product", "Total"], "answer": "Difference", "difficulty": "medium", "topic": "Subtraction"},
        {"question": "The minus sign means subtract.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Subtraction"},
        {"question": "When we take 2 away from 5 we get ___.", "type": "FillBlank", "options": [], "answer": "3", "difficulty": "easy", "topic": "Subtraction"},
        # Patterns
        {"question": "What can patterns use to repeat?", "type": "MCQ", "options": ["Only colors", "Only shapes", "Colors, shapes, or numbers", "Only numbers"], "answer": "Colors, shapes, or numbers", "difficulty": "medium", "topic": "Patterns"},
        {"question": "Patterns repeat themselves.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Patterns"},
        {"question": "Finding patterns helps us ___ what comes next.", "type": "FillBlank", "options": [], "answer": "predict", "difficulty": "medium", "topic": "Patterns"},
    ],
    "English": [
        {"question": "What is a noun?", "type": "MCQ", "options": ["An action word", "A describing word", "A word that names a person, place, thing, or idea", "A connecting word"], "answer": "A word that names a person, place, thing, or idea", "difficulty": "easy", "topic": "Nouns"},
        {"question": "Proper nouns name specific people or places and are capitalized.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Nouns"},
        {"question": "A ___ is a word that names a person, place, thing, or idea.", "type": "FillBlank", "options": [], "answer": "noun", "difficulty": "easy", "topic": "Nouns"},
        {"question": "What must every sentence have?", "type": "MCQ", "options": ["A noun only", "A verb only", "A subject and a predicate", "An adjective"], "answer": "A subject and a predicate", "difficulty": "medium", "topic": "Sentences"},
        {"question": "A verb is a describing word.", "type": "TrueFalse", "options": ["True", "False"], "answer": "False", "difficulty": "easy", "topic": "Verbs"},
        {"question": "Every sentence must have a ___.", "type": "FillBlank", "options": [], "answer": "verb", "difficulty": "easy", "topic": "Verbs"},
        {"question": "Which punctuation ends a question?", "type": "MCQ", "options": ["Period", "Comma", "Exclamation mark", "Question mark"], "answer": "Question mark", "difficulty": "easy", "topic": "Punctuation"},
        {"question": "A period ends a question.", "type": "TrueFalse", "options": ["True", "False"], "answer": "False", "difficulty": "easy", "topic": "Punctuation"},
        {"question": "A ___ ends a statement.", "type": "FillBlank", "options": [], "answer": "period", "difficulty": "easy", "topic": "Punctuation"},
        {"question": "What does an adjective describe?", "type": "MCQ", "options": ["A verb", "A noun", "An adverb", "A sentence"], "answer": "A noun", "difficulty": "medium", "topic": "Adjectives"},
        {"question": "Adjectives can tell us how many.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Adjectives"},
        {"question": "An ___ describes a noun.", "type": "FillBlank", "options": [], "answer": "adjective", "difficulty": "easy", "topic": "Adjectives"},
        {"question": "What is the subject of a sentence?", "type": "MCQ", "options": ["The action", "Who or what the sentence is about", "The punctuation", "The describing word"], "answer": "Who or what the sentence is about", "difficulty": "medium", "topic": "Sentences"},
        {"question": "Verbs can be in past, present, or future tense.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "medium", "topic": "Verbs"},
        {"question": "The ___ tells what the subject does or is.", "type": "FillBlank", "options": [], "answer": "predicate", "difficulty": "hard", "topic": "Sentences"},
    ],
    "Science": [
        {"question": "What process do plants use to make food?", "type": "MCQ", "options": ["Digestion", "Respiration", "Photosynthesis", "Germination"], "answer": "Photosynthesis", "difficulty": "easy", "topic": "Photosynthesis"},
        {"question": "Plants release oxygen during photosynthesis.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Photosynthesis"},
        {"question": "Plants make food using sunlight, water, and carbon ___.", "type": "FillBlank", "options": [], "answer": "dioxide", "difficulty": "medium", "topic": "Photosynthesis"},
        {"question": "What do roots do?", "type": "MCQ", "options": ["Capture sunlight", "Absorb water and nutrients from soil", "Carry water to flowers", "Make seeds"], "answer": "Absorb water and nutrients from soil", "difficulty": "easy", "topic": "Plant Parts"},
        {"question": "Leaves capture sunlight to make food.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Plant Parts"},
        {"question": "The ___ carries water to the rest of the plant.", "type": "FillBlank", "options": [], "answer": "stem", "difficulty": "easy", "topic": "Plant Parts"},
        {"question": "Which animal group has feathers?", "type": "MCQ", "options": ["Mammals", "Reptiles", "Birds", "Fish"], "answer": "Birds", "difficulty": "easy", "topic": "Animal Groups"},
        {"question": "Mammals are cold-blooded.", "type": "TrueFalse", "options": ["True", "False"], "answer": "False", "difficulty": "medium", "topic": "Animal Groups"},
        {"question": "Animals that eat plants are called ___.", "type": "FillBlank", "options": [], "answer": "herbivores", "difficulty": "medium", "topic": "Food Chain"},
        {"question": "What are plants called in a food chain?", "type": "MCQ", "options": ["Consumers", "Producers", "Decomposers", "Predators"], "answer": "Producers", "difficulty": "medium", "topic": "Food Chain"},
        {"question": "A food chain shows how energy moves through living things.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Food Chain"},
        {"question": "A ___ is where a plant or animal lives.", "type": "FillBlank", "options": [], "answer": "habitat", "difficulty": "easy", "topic": "Habitats"},
        {"question": "Which habitat is hot and dry?", "type": "MCQ", "options": ["Ocean", "Forest", "Desert", "Tundra"], "answer": "Desert", "difficulty": "easy", "topic": "Habitats"},
        {"question": "Animals are adapted to survive in their habitats.", "type": "TrueFalse", "options": ["True", "False"], "answer": "True", "difficulty": "easy", "topic": "Habitats"},
        {"question": "Fish breathe through ___.", "type": "FillBlank", "options": [], "answer": "gills", "difficulty": "medium", "topic": "Animal Groups"},
    ],
}

STUDENTS = [
    {"id": "S001", "name": "Alex Chen", "difficulty": "medium"},
    {"id": "S002", "name": "Priya Sharma", "difficulty": "easy"},
    {"id": "S003", "name": "Marcus Johnson", "difficulty": "hard"},
]


def seed():
    init_db()
    db = SessionLocal()

    try:
        # Check if already seeded
        if db.query(Document).count() > 0:
            print("⚠  Database already has data. Run with --force to re-seed.")
            return

        print("🌱 Seeding database...")
        chunk_map = {}   # subject → list of chunk ids

        # ── Documents & Chunks ──────────────────────────────────────────────
        for doc_data in DOCUMENTS:
            doc_id = str(uuid.uuid4())
            doc = Document(
                id=doc_id,
                file_name=doc_data["file_name"],
                subject=doc_data["subject"],
                grade=doc_data["grade"],
                total_pages=10,
                total_chunks=len(doc_data["chunks"]),
                status="processed",
                uploaded_at=datetime.utcnow() - timedelta(days=random.randint(1, 7)),
            )
            db.add(doc)
            db.flush()

            chunk_ids = []
            for i, ch in enumerate(doc_data["chunks"]):
                cid = str(uuid.uuid4())
                chunk = Chunk(
                    id=cid,
                    document_id=doc_id,
                    chunk_index=i,
                    topic=ch["topic"],
                    text=ch["text"],
                    word_count=len(ch["text"].split()),
                )
                db.add(chunk)
                chunk_ids.append((cid, ch["topic"]))

            chunk_map[doc_data["subject"]] = chunk_ids
            print(f"  ✓ Document: {doc_data['file_name']} ({len(doc_data['chunks'])} chunks)")

        db.flush()

        # ── Questions ────────────────────────────────────────────────────────
        question_ids_by_difficulty = {"easy": [], "medium": [], "hard": []}
        all_question_ids = []

        for subject, questions in QUESTIONS_TEMPLATE.items():
            chunks = chunk_map[subject]
            for q_data in questions:
                # Find matching chunk by topic
                chunk_id = next(
                    (cid for cid, t in chunks if t == q_data["topic"]),
                    chunks[0][0]
                )
                qid = str(uuid.uuid4())
                q = Question(
                    id=qid,
                    chunk_id=chunk_id,
                    question=q_data["question"],
                    question_type=q_data["type"],
                    options_json=json.dumps(q_data["options"]),
                    answer=q_data["answer"],
                    difficulty=q_data["difficulty"],
                    topic=q_data["topic"],
                    subject=subject,
                    grade={"Math": 1, "English": 4, "Science": 3}[subject],
                )
                db.add(q)
                question_ids_by_difficulty[q_data["difficulty"]].append((qid, q_data["answer"]))
                all_question_ids.append((qid, q_data["answer"], subject, q_data["difficulty"]))

        db.flush()
        print(f"  ✓ {len(all_question_ids)} questions created")

        # ── Student Profiles & Answer History ───────────────────────────────
        for s_data in STUDENTS:
            student = StudentProfile(
                id=str(uuid.uuid4()),
                student_id=s_data["id"],
                display_name=s_data["name"],
                current_difficulty=s_data["difficulty"],
                last_active=datetime.utcnow() - timedelta(hours=random.randint(1, 48)),
            )
            db.add(student)
            db.flush()

            # Generate answer history (20 answers with realistic accuracy)
            accuracy_target = {"S001": 0.75, "S002": 0.55, "S003": 0.88}[s_data["id"]]
            sample = random.sample(all_question_ids, min(20, len(all_question_ids)))
            correct_count = 0
            streak = 0
            best_streak = 0

            for i, (qid, correct_ans, subj, diff) in enumerate(sample):
                is_correct = random.random() < accuracy_target
                selected = correct_ans if is_correct else "wrong_answer"
                if is_correct:
                    correct_count += 1
                    streak += 1
                    best_streak = max(best_streak, streak)
                else:
                    streak = 0

                ans = StudentAnswer(
                    id=str(uuid.uuid4()),
                    student_id=s_data["id"],
                    question_id=qid,
                    selected_answer=selected,
                    is_correct=is_correct,
                    time_taken_seconds=random.randint(5, 45),
                    difficulty_at_attempt=diff,
                    hint_used=random.random() < 0.15,
                    submitted_at=datetime.utcnow() - timedelta(minutes=random.randint(10, 1440)),
                )
                db.add(ans)

            student.total_attempted = len(sample)
            student.total_correct = correct_count
            student.streak_current = streak
            student.streak_best = best_streak

            # Add 2 bookmarks per student
            bm_sample = random.sample(all_question_ids, 2)
            for qid, _, _, _ in bm_sample:
                bm = Bookmark(
                    id=str(uuid.uuid4()),
                    student_id=s_data["id"],
                    question_id=qid,
                    note="Review this topic again",
                )
                db.add(bm)

            print(f"  ✓ Student {s_data['name']} ({s_data['id']}): {correct_count}/{len(sample)} correct, streak {best_streak}")

        # ── Cheat Sessions ──────────────────────────────────────────────────
        # Clean session
        clean_session = CheatSession(
            id=str(uuid.uuid4()),
            student_id="S001",
            session_token=str(uuid.uuid4()),
            started_at=datetime.utcnow() - timedelta(minutes=30),
            ended_at=datetime.utcnow() - timedelta(minutes=10),
            risk_score=0,
            is_flagged=False,
        )
        db.add(clean_session)
        db.flush()

        # Flagged session for S002
        flagged_session = CheatSession(
            id=str(uuid.uuid4()),
            student_id="S002",
            session_token=str(uuid.uuid4()),
            started_at=datetime.utcnow() - timedelta(hours=2),
            ended_at=datetime.utcnow() - timedelta(hours=1, minutes=30),
            risk_score=75,
            is_flagged=True,
            flag_reason="High-risk activity detected: devtools_open ×1, copy_paste ×1, fast_submit ×1",
        )
        db.add(flagged_session)
        db.flush()

        for ev_type in ["devtools_open", "copy_paste", "fast_submit"]:
            db.add(CheatEvent(
                id=str(uuid.uuid4()),
                session_id=flagged_session.id,
                event_type=ev_type,
                detail=f"Detected: {ev_type}",
                recorded_at=datetime.utcnow() - timedelta(hours=1, minutes=45),
            ))

        db.commit()
        print("\n✅ Seed complete!")
        print("\n  Try these endpoints:")
        print("  GET  http://localhost:8000/api/v1/documents")
        print("  GET  http://localhost:8000/api/v1/quiz?difficulty=easy&num_questions=5")
        print("  GET  http://localhost:8000/api/v1/quiz?topic=Shapes&subject=Math")
        print("  GET  http://localhost:8000/api/v1/students/S001/dashboard")
        print("  GET  http://localhost:8000/api/v1/students/S002/integrity")
        print("  GET  http://localhost:8000/api/v1/questions/stats")
        print("  GET  http://localhost:8000/docs")

    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    if "--force" in sys.argv:
        from app.database.db import engine
        from app.models.database_models import Base
        Base.metadata.drop_all(bind=engine)
        print("🗑  Dropped all tables")
    seed()
