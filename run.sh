#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Peblo AI Quiz Engine — Quick Start Script
# Usage: bash run.sh
# ─────────────────────────────────────────────────────────────

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ██████╗ ███████╗██████╗ ██╗      ██████╗ "
echo "  ██╔══██╗██╔════╝██╔══██╗██║     ██╔═══██╗"
echo "  ██████╔╝█████╗  ██████╔╝██║     ██║   ██║"
echo "  ██╔═══╝ ██╔══╝  ██╔══██╗██║     ██║   ██║"
echo "  ██║     ███████╗██████╔╝███████╗╚██████╔╝"
echo "  ╚═╝     ╚══════╝╚═════╝ ╚══════╝ ╚═════╝ "
echo "         AI Quiz Engine v1.0"
echo -e "${NC}"

# ── Check Python ──────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 not found. Please install Python 3.10+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "Python version: ${GREEN}${PYTHON_VERSION}${NC}"

# ── .env check ───────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}No .env found — copying from .env.example${NC}"
    cp .env.example .env
    echo -e "${RED}⚠  Please edit .env and add your GEMINI_API_KEY before running again.${NC}"
    echo "   Get a free key at: https://aistudio.google.com/app/apikey"
    exit 1
fi

# Check for placeholder key
if grep -q "your_gemini_api_key_here" .env; then
    echo -e "${RED}⚠  .env still has placeholder GEMINI_API_KEY.${NC}"
    echo "   Edit .env and add your real key from: https://aistudio.google.com/app/apikey"
    exit 1
fi

echo -e "${GREEN}✓ .env configured${NC}"

# ── Virtual environment ───────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment active${NC}"

# ── Install dependencies ──────────────────────────────────────
echo "Installing dependencies..."
pip install -r requirements.txt -q
echo -e "${GREEN}✓ Dependencies installed${NC}"

# ── Create upload directory ───────────────────────────────────
mkdir -p uploads
echo -e "${GREEN}✓ Upload directory ready${NC}"

# ── Run ───────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}Starting Peblo AI Quiz Engine...${NC}"
echo -e "  API:  ${GREEN}http://localhost:8000${NC}"
echo -e "  Docs: ${GREEN}http://localhost:8000/docs${NC}"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
