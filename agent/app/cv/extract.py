"""Extracts plain text from the uploaded CV file.

A deliberate trade-off: not every provider accepts a PDF as a `document` block,
so the text is extracted locally instead. Standard single-column CVs are fine;
heavily designed, two-column or table-based PDFs can come out in the wrong
reading order. If extraction yields nothing useful we point the user at
DOCX/TXT — a clear error beats silently working from garbled text.
"""

from __future__ import annotations

import io

from docx import Document
from pypdf import PdfReader

MAX_TEXT_CHARS = 200_000
#: Below this, the PDF is a scanned image with no text layer
MIN_USEFUL_CHARS = 120

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class UnsupportedCV(ValueError):
    pass


def _suffix(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _docx_to_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    lines = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(line for line in lines if line.strip())


def _pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - one broken page must not fail the whole CV
            continue
    return "\n".join(pages)


def to_text(filename: str, data: bytes) -> str:
    """Converts the CV file into plain text for the model."""
    suffix = _suffix(filename)
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedCV(
            f"Unsupported file type: {suffix or 'no extension'}. "
            f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    if not data:
        raise UnsupportedCV("The file is empty.")

    if suffix == ".pdf":
        text = _pdf_to_text(data)
        if len(text.strip()) < MIN_USEFUL_CHARS:
            raise UnsupportedCV(
                "Could not extract text from the PDF — it may be a scanned image. "
                "Upload the CV as DOCX or TXT instead."
            )
    elif suffix == ".docx":
        text = _docx_to_text(data)
    else:
        text = data.decode("utf-8", errors="replace")

    if len(text.strip()) < MIN_USEFUL_CHARS:
        raise UnsupportedCV("No readable text could be extracted from the file.")
    return text[:MAX_TEXT_CHARS]
