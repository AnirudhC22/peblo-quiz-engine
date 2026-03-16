"""
PDF Parser Service
Extracts text from PDF, cleans it, and produces smart semantic chunks.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RawChunk:
    chunk_id: str
    chunk_index: int
    topic: Optional[str]
    text: str
    word_count: int


@dataclass
class ParsedDocument:
    file_name: str
    subject: str
    grade: int
    total_pages: int
    chunks: list[RawChunk] = field(default_factory=list)


def _extract_text_pymupdf(pdf_path: str) -> tuple[list[str], int]:
    """Extract page texts using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        pages = [page.get_text() for page in doc]
        total = len(pages)
        doc.close()
        return pages, total
    except ImportError:
        logger.warning("PyMuPDF not available, falling back to pdfplumber")
        return _extract_text_pdfplumber(pdf_path)


def _extract_text_pdfplumber(pdf_path: str) -> tuple[list[str], int]:
    """Fallback: extract using pdfplumber."""
    import pdfplumber
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages, len(pages)


def _clean_text(text: str) -> str:
    """
    Remove PDF noise: page numbers, headers, footers, repeated whitespace.
    """
    # Remove standalone page numbers like "Page 3", "3", "- 3 -"
    text = re.sub(r"(?m)^[-\s]*Page\s+\d+\s*[-\s]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?m)^\s*\d+\s*$", "", text)
    text = re.sub(r"(?m)^-\s*\d+\s*-$", "", text)

    # Remove repeated dashes/underscores (decorative lines)
    text = re.sub(r"[-_=]{4,}", "", text)

    # Normalize multiple newlines to max 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalize whitespace within lines
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r" {2,}", " ", line).strip()
        if cleaned:
            lines.append(cleaned)

    return "\n".join(lines).strip()


def _detect_topic(text: str) -> Optional[str]:
    """
    Heuristic: first bold-like or ALL-CAPS line is likely a heading/topic.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Check for heading patterns: ALL CAPS, ends with ':', or short first line
        if stripped.isupper() and len(stripped) > 3:
            return stripped.title()
        if stripped.endswith(":") and len(stripped.split()) <= 6:
            return stripped.rstrip(":")
        if len(stripped.split()) <= 8 and stripped[0].isupper():
            return stripped
    return None


def _semantic_chunk(pages: list[str], chunk_size: int = 300) -> list[RawChunk]:
    """
    Smart semantic chunking:
    1. Split on paragraph boundaries first
    2. Group paragraphs until word limit reached
    3. Never cut mid-sentence
    """
    full_text = "\n\n".join(pages)
    cleaned = _clean_text(full_text)

    # Split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]

    chunks = []
    current_words = []
    current_paragraphs = []
    chunk_index = 0

    for para in paragraphs:
        words = para.split()
        if not words:
            continue

        # If adding this paragraph exceeds limit, flush current chunk
        if current_words and len(current_words) + len(words) > chunk_size:
            chunk_text = "\n\n".join(current_paragraphs)
            chunks.append(RawChunk(
                chunk_id=f"CH_{chunk_index:04d}",
                chunk_index=chunk_index,
                topic=_detect_topic(chunk_text),
                text=chunk_text,
                word_count=len(current_words),
            ))
            chunk_index += 1
            current_words = []
            current_paragraphs = []

        current_words.extend(words)
        current_paragraphs.append(para)

    # Flush remaining content
    if current_paragraphs:
        chunk_text = "\n\n".join(current_paragraphs)
        chunks.append(RawChunk(
            chunk_id=f"CH_{chunk_index:04d}",
            chunk_index=chunk_index,
            topic=_detect_topic(chunk_text),
            text=chunk_text,
            word_count=len(current_words),
        ))

    # Filter out very short chunks (likely noise)
    chunks = [c for c in chunks if c.word_count >= 20]

    logger.info(f"Produced {len(chunks)} semantic chunks")
    return chunks


def _infer_metadata(file_name: str) -> tuple[str, int]:
    """
    Infer subject and grade from file name pattern like:
    peblo_pdf_grade4_english_grammar.pdf
    """
    name = Path(file_name).stem.lower()

    # Extract grade
    grade_match = re.search(r"grade(\d+)", name)
    grade = int(grade_match.group(1)) if grade_match else 1

    # Extract subject keywords
    subject_keywords = {
        "math": "Math",
        "english": "English",
        "grammar": "English",
        "science": "Science",
        "history": "History",
        "social": "Social Studies",
    }
    subject = "General"
    for kw, label in subject_keywords.items():
        if kw in name:
            subject = label
            break

    return subject, grade


def parse_pdf(pdf_path: str, chunk_size: int = 300) -> ParsedDocument:
    """
    Main entry point: parse PDF → clean → chunk → return ParsedDocument.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    file_name = path.name
    subject, grade = _infer_metadata(file_name)

    logger.info(f"Parsing PDF: {file_name} | Subject: {subject} | Grade: {grade}")

    pages, total_pages = _extract_text_pymupdf(str(path))
    chunks = _semantic_chunk(pages, chunk_size=chunk_size)

    return ParsedDocument(
        file_name=file_name,
        subject=subject,
        grade=grade,
        total_pages=total_pages,
        chunks=chunks,
    )
