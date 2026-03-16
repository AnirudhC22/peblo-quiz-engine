# Peblo AI Quiz Engine — Makefile
# Usage: make <target>

.PHONY: help setup run seed test lint clean reset

VENV=venv
PYTHON=$(VENV)/bin/python
PIP=$(VENV)/bin/pip
UVICORN=$(VENV)/bin/uvicorn
PYTEST=$(VENV)/bin/pytest

help:
	@echo ""
	@echo "  Peblo AI Quiz Engine"
	@echo ""
	@echo "  make setup    Install dependencies into virtualenv"
	@echo "  make run      Start the API server (hot reload)"
	@echo "  make seed     Populate DB with demo data"
	@echo "  make test     Run all tests"
	@echo "  make lint     Check code with pyflakes"
	@echo "  make clean    Remove .db, uploads, __pycache__"
	@echo "  make reset    Drop DB and re-seed"
	@echo ""

setup:
	@echo "Creating virtual environment..."
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip -q
	$(PIP) install -r requirements.txt -q
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env — add your GEMINI_API_KEY"; fi
	@echo "✓ Setup complete. Edit .env then run: make run"

run:
	@if [ ! -f .env ]; then echo "No .env file. Run: make setup"; exit 1; fi
	mkdir -p uploads
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

seed:
	$(PYTHON) seed.py

seed-force:
	$(PYTHON) seed.py --force

test:
	$(PYTEST) tests/ -v

test-unit:
	$(PYTEST) tests/test_full.py -v -k "not TestIngestion"

test-cov:
	$(PYTEST) tests/ -v --tb=short

lint:
	@$(PYTHON) -m py_compile app/main.py app/api/*.py app/services/*.py app/models/*.py app/database/*.py
	@echo "✓ No syntax errors"

clean:
	rm -f *.db
	rm -rf uploads/
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleaned"

reset: clean
	$(PYTHON) seed.py --force
	@echo "✓ Database reset and re-seeded"
