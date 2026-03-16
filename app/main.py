"""
Peblo AI Quiz Engine - Main Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ingest_routes, monitor_routes, quiz_routes, student_routes
from app.database.db import init_db
from app.middleware import RateLimitMiddleware, RequestLoggingMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Peblo Quiz Engine...")
    init_db()
    logger.info("✅ Database initialized")
    yield
    logger.info("🛑 Shutting down Peblo Quiz Engine")


app = FastAPI(
    title="Peblo AI Quiz Engine",
    description="""
    An AI-powered content ingestion and adaptive quiz engine.
    
    ## Features
    - 📄 PDF ingestion with smart chunking
    - 🤖 LLM-powered quiz generation (OpenAI / Anthropic / Gemini)
    - 🎯 Adaptive difficulty based on student performance
    - 💡 AI-powered hint system
    - 📊 Learning streaks & progress dashboard
    - 🔖 Bookmark weak questions for re-attempts
    - 🛠️ Student quiz customizer
    """,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_routes.router, prefix="/api/v1", tags=["Ingestion"])
app.include_router(quiz_routes.router, prefix="/api/v1", tags=["Quiz"])
app.include_router(monitor_routes.router, prefix="/api/v1", tags=["Integrity Monitor"])
app.include_router(student_routes.router, prefix="/api/v1", tags=["Student"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "Peblo AI Quiz Engine",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
