"""
Ingestion Routes
POST /ingest — Upload PDF, extract, chunk, store
"""

import logging
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.database_models import Chunk, Document
from app.models.schemas import IngestResponse
from app.services.pdf_parser import parse_pdf

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/ingest", response_model=IngestResponse, summary="Ingest a PDF file")
async def ingest_pdf(
    file: UploadFile = File(..., description="PDF file to ingest"),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF file and extract educational content chunks.
    
    - Accepts PDF files only
    - Extracts and cleans text
    - Performs semantic chunking
    - Stores document and chunks in the database
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Save uploaded file temporarily
    doc_id = str(uuid.uuid4())
    tmp_path = UPLOAD_DIR / f"{doc_id}_{file.filename}"

    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(f"Saved uploaded file: {tmp_path}")

        # Parse PDF
        parsed = parse_pdf(str(tmp_path))

        if not parsed.chunks:
            raise HTTPException(status_code=422, detail="No readable content extracted from PDF.")

        # Store document record
        doc = Document(
            id=doc_id,
            file_name=parsed.file_name,
            subject=parsed.subject,
            grade=parsed.grade,
            total_pages=parsed.total_pages,
            total_chunks=len(parsed.chunks),
            status="processed",
        )
        db.add(doc)
        db.flush()

        # Store chunks
        for raw_chunk in parsed.chunks:
            chunk = Chunk(
                id=str(uuid.uuid4()),
                document_id=doc_id,
                chunk_index=raw_chunk.chunk_index,
                topic=raw_chunk.topic,
                text=raw_chunk.text,
                word_count=raw_chunk.word_count,
            )
            db.add(chunk)

        db.commit()
        logger.info(f"Ingested document {doc_id}: {len(parsed.chunks)} chunks")

        return IngestResponse(
            document_id=doc_id,
            file_name=parsed.file_name,
            subject=parsed.subject,
            grade=parsed.grade,
            total_pages=parsed.total_pages,
            chunks_created=len(parsed.chunks),
            message=f"Successfully ingested {len(parsed.chunks)} content chunks.",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@router.get("/documents", summary="List all ingested documents")
def list_documents(db: Session = Depends(get_db)):
    """Return all ingested source documents."""
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    return [
        {
            "id": d.id,
            "file_name": d.file_name,
            "subject": d.subject,
            "grade": d.grade,
            "total_pages": d.total_pages,
            "total_chunks": d.total_chunks,
            "status": d.status,
            "uploaded_at": d.uploaded_at,
        }
        for d in docs
    ]


@router.get("/documents/{document_id}/chunks", summary="Preview chunks for a document")
def get_document_chunks(document_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """Return content chunks for a given document (for inspection/debugging)."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .limit(limit)
        .all()
    )
    return {
        "document_id": document_id,
        "file_name": doc.file_name,
        "subject": doc.subject,
        "grade": doc.grade,
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "topic": c.topic,
                "word_count": c.word_count,
                "text_preview": c.text[:300] + ("..." if len(c.text) > 300 else ""),
            }
            for c in chunks
        ],
    }
