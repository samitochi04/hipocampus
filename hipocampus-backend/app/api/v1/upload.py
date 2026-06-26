"""
app/api/v1/upload.py

Document upload and text extraction endpoint.
Accepts a single file attachment, validates it, extracts readable text,
and returns the text so the frontend can prepend it to the next chat message.

Security model:
  1. Extension whitelist — only .pdf, .csv, .md accepted.
  2. Double-extension check — "malware.exe.pdf" is rejected before any reading.
     Implemented by checking whether the stem of the filename itself carries
     an extension (Path("malware.exe").suffix → ".exe" → blocked).
  3. Size cap — reading stops at 10 MB; if the file is larger the request
     is rejected with 413 before the full body is buffered.
  4. Auth-gated — requires a valid Bearer token; anonymous uploads are blocked.

Text extraction by format:
  .pdf  — PyMuPDF (fitz) page-by-page text extraction.
          Returns plain text with page separators.
  .csv  — csv.reader; formats rows as "col1 | col2 | col3" lines so the AI
          can parse the structure without needing actual CSV parsing.
  .md   — UTF-8 decode; the AI handles Markdown natively.

All extracted text is capped at 80,000 characters to keep it within Qwen's
context window when combined with memory context and the system prompt.

Used by: app/api/v1/router.py, src/api/upload.js.
"""

import csv
import io
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.dependencies import get_current_user
from app.schemas.auth import UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_BYTES     = 10 * 1024 * 1024   # 10 MB read cap
MAX_CHARS     = 80_000              # extracted text cap
ALLOWED_EXTS  = {".pdf", ".csv", ".md"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_extension(filename: str) -> str:
    """
    Returns the lowercased file extension and raises 400 if:
      - The filename has no extension.
      - The extension is not in the whitelist.
      - The stem itself carries an extension (double-extension attack:
        "invoice.exe.pdf" → stem "invoice.exe" → suffix ".exe" → blocked).

    Parameters:
        filename (str) — the original filename from the upload.

    Returns:
        str — the validated lowercased extension, e.g. ".pdf".

    Raises:
        HTTPException 400 — any validation failure.
    """
    # Strip path components — only trust the final filename segment.
    name = Path(filename).name
    ext  = Path(name).suffix.lower()

    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has no extension. Only .pdf, .csv, and .md are accepted.",
        )

    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension '{ext}' is not allowed. Accepted: .pdf, .csv, .md",
        )

    # Double-extension guard: "file.exe.pdf" → stem = "file.exe" → suffix = ".exe"
    stem_ext = Path(Path(name).stem).suffix
    if stem_ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Filename '{name}' looks suspicious (double extension "
                f"'{stem_ext}{ext}'). Upload rejected for security."
            ),
        )

    return ext


def _extract_pdf(content: bytes) -> str:
    """
    Extracts plain text from a PDF binary using PyMuPDF (fitz).
    Inserts a '--- Page N ---' separator between pages.

    Parameters:
        content (bytes) — raw PDF bytes.

    Returns:
        str — extracted text, capped at MAX_CHARS.

    Raises:
        HTTPException 422 — file is not a valid PDF.
    """
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        logger.warning("PDF open failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not read the PDF. The file may be corrupted or encrypted.",
        )

    parts: list[str] = []
    for i, page in enumerate(doc, start=1):
        page_text = page.get_text().strip()
        if page_text:
            parts.append(f"--- Page {i} ---\n{page_text}")

    doc.close()
    full = "\n\n".join(parts).strip()
    if not full:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No readable text found in the PDF (it may be image-only or scanned).",
        )
    return full[:MAX_CHARS]


def _extract_csv(content: bytes) -> str:
    """
    Decodes a CSV file and formats it as pipe-delimited text rows that the
    AI can parse without CSV parsing logic.

    Parameters:
        content (bytes) — raw CSV bytes.

    Returns:
        str — formatted text, capped at MAX_CHARS.
    """
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows: list[str] = []
    for row in reader:
        rows.append(" | ".join(cell.strip() for cell in row))
    return "\n".join(rows)[:MAX_CHARS]


def _extract_md(content: bytes) -> str:
    """
    Decodes Markdown as UTF-8 (the AI handles Markdown natively).

    Parameters:
        content (bytes) — raw Markdown bytes.

    Returns:
        str — decoded text, capped at MAX_CHARS.
    """
    return content.decode("utf-8", errors="replace")[:MAX_CHARS]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=200,
    summary="Upload a document and extract its text",
)
async def upload_document(
    file: UploadFile,
    current_user: UserOut = Depends(get_current_user),
) -> dict:
    """
    Validates and extracts text from an uploaded file.

    The extracted text is returned to the frontend so it can be prepended
    to the user's next chat message in the format:
        [DOCUMENT: filename.pdf]
        {extracted_text}
        ---
        {user_message}

    This allows the AI to read the document content and respond to it
    within the same context window, without any separate RAG pipeline.

    Parameters:
        file         (UploadFile) — multipart file from the form.
        current_user (UserOut)    — authenticated user.

    Returns:
        dict — {
            filename:       str,   original filename
            format:         str,   "pdf" | "csv" | "md"
            char_count:     int,   length of extracted_text
            extracted_text: str,   the text to prepend to the next message
        }

    Raises:
        HTTPException 400  — bad filename / extension / double-extension.
        HTTPException 413  — file exceeds 10 MB.
        HTTPException 422  — file is unreadable (corrupted PDF, etc.).
    """
    # Validate filename and extension.
    ext = _safe_extension(file.filename or "untitled")
    logger.info(
        "Upload: filename=%s ext=%s user=%s",
        file.filename, ext, current_user.id,
    )

    # Read with size cap — stop immediately if the file is too large.
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 10 MB limit. Please upload a smaller file.",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty.",
        )

    # Extract text by format.
    if ext == ".pdf":
        extracted = _extract_pdf(content)
        fmt = "pdf"
    elif ext == ".csv":
        extracted = _extract_csv(content)
        fmt = "csv"
    else:  # .md
        extracted = _extract_md(content)
        fmt = "md"

    logger.info(
        "Extracted %d chars from %s for user %s",
        len(extracted), file.filename, current_user.id,
    )

    return {
        "filename":       Path(file.filename or "document").name,
        "format":         fmt,
        "char_count":     len(extracted),
        "extracted_text": extracted,
    }