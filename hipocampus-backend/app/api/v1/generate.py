"""
app/api/v1/generate.py

AI document generation endpoint.
Accepts a plain-text prompt and a desired output format, calls Qwen-Max to
generate structured content, and returns a ready-to-download file.

Supported formats:
  md   — Markdown  (.md)  — returned as UTF-8 text.
  pdf  — PDF       (.pdf) — Markdown converted to PDF via fpdf2 (pure Python,
                             no system-level dependencies).
  csv  — CSV       (.csv) — Qwen is prompted to return raw CSV, no wrappers.

Page sizes (PDF only):
  A4 (default) — 210 × 297 mm
  A3           — 297 × 420 mm

The endpoint is auth-protected — the generated content is attributed to the
requesting user. No memory is updated; this is a one-shot generation.

Used by: app/api/v1/router.py, src/api/generate.js.
"""

import logging
import re
from datetime import UTC, datetime

import httpx

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.dependencies import get_current_user
from app.schemas.auth import UserOut
from app.services.memory_engine.qwen_router import generate, generate_with_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generate"])

# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """
    Body for POST /generate.

    Parameters:
        prompt  (str)  — plain-text description of what to generate.
        format  (str)  — "md" | "pdf" | "csv"
        size    (str)  — "A4" | "A3". Ignored for md/csv. Default "A4".
    """

    prompt: str = Field(..., min_length=5, max_length=2000)
    format: str = Field(..., pattern="^(md|pdf|csv)$")
    size:   str = Field(default="A4", pattern="^(A4|A3)$")


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_DOC_SYSTEM = """You are an expert professional document writer.

CRITICAL DECISION — read before anything else:
1. Does the user's request contain inline data (numbers, financial figures, tables, metrics, Q1/Q2 values)?
   YES → USE THAT DATA DIRECTLY. Do NOT call web_search at all.
   NO → go to step 2.
2. Does the user ask for CURRENT real-world data from a real organisation that they have NOT provided?
   YES → call web_search with a precise factual query.
   NO → generate from your knowledge.

NEVER call web_search for:
- Company logos, images, branding — skip those elements entirely.
- Data the user has already supplied in the prompt.
- Fictional or hypothetical companies.

OUTPUT RULES — these are absolute:
- Output ONLY the document content. Zero preamble, zero commentary, zero sign-off.
- Do NOT add any section titled "Instructions", "How to convert", "Next steps",
  "Page Numbers", or anything that is not part of the actual document.
- Do NOT write placeholder phrases like "Add logo here", "Insert chart here",
  or "Use a PDF converter" — simply omit elements that cannot be text.
- Page numbers are injected automatically — do not mention them in the content.
- Your output is converted to PDF immediately — write final document content only.

Use proper Markdown:
  # Title              — one document title
  ## Section           — major section headings
  ### Subsection       — subsection headings
  - bullet / 1. item   — lists
  **bold**             — key terms
  | col | col |        — tables for all numerical data (always use tables for numbers)

When financial data is provided: open with an executive summary, use one table per
data section with percentage changes, and close with concrete recommendations.
Be thorough and professional."""

_CSV_SYSTEM = """You are a data analyst generating CSV files.

CRITICAL DECISION:
1. Did the user provide the data inline? YES → use it directly, do NOT search.
2. Does the user need CURRENT real-world data not provided? YES → call web_search.
3. Never invent numbers. If data is unavailable after searching, add a comment row.

NEVER search for logos, images, or data already present in the prompt.

Return ONLY raw CSV — no markdown, no code fences, no explanation.
Start with the header row. Use commas as delimiters. Quote strings containing commas."""


# ---------------------------------------------------------------------------
# URL content fetcher
# ---------------------------------------------------------------------------


async def _fetch_url(url: str, max_chars: int = 25_000) -> str:
    """
    Fetches a URL and returns its visible text content.
    Used when the user's generation prompt contains a URL — the page
    content is injected as context so the AI can use real data.

    Parameters:
        url       (str) — the URL to fetch.
        max_chars (int) — character cap on the extracted text.

    Returns:
        str — plain text extracted from the page, or an error message.
    """
    import re as _re
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Hipocampus/1.0)"},
            )
        # Strip HTML tags and collapse whitespace.
        text = _re.sub(r"<[^>]+>", " ", resp.text)
        text = _re.sub(r"\s{2,}", " ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        logger.warning("URL fetch failed for %s: %s", url, exc)
        return f"[Could not fetch {url}: {exc}]"


# ---------------------------------------------------------------------------
# PDF renderer (Markdown → fpdf2)
# ---------------------------------------------------------------------------


def _markdown_to_pdf(content: str, page_size: str) -> bytes:
    """
    Markdown → PDF via fpdf2.

    Key robustness rules:
    - Explicit new_x=XPos.LEFT, new_y=YPos.NEXT on every multi_cell so the
      cursor is always reset to (l_margin, next_line) — no cursor drift.
    - pdf.x is reset to M at the top of every line iteration as an extra guard.
    - Table separator rows (|---|---) are silently skipped.
    - Markdown tables are rendered as plain pipe-delimited text rows.
    - _safe() breaks tokens > 65 chars so fpdf2 always fits one fragment.
    - Every render call is wrapped in try/except — one bad line is skipped,
      not the whole document.
    """
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    M      = 20   # base margin mm
    IND    = 6    # bullet / list indent mm

    def _safe(text: str, n: int = 65) -> str:
        out = []
        for word in text.split():
            if len(word) > n:
                out.extend(word[i:i+n] for i in range(0, len(word), n))
            else:
                out.append(word)
        return " ".join(out)

    def _strip(t: str) -> str:
        t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)
        t = re.sub(r'\*(.+?)\*',     r'\1', t)
        t = re.sub(r'`(.+?)`',       r'\1', t)
        return t

    def cell(text: str, h: int = 6, font: str = "", size: int = 11,
             color=(0,0,0), lm: int = M) -> None:
        """Safe multi_cell wrapper — always resets cursor, catches errors."""
        pdf.set_left_margin(lm)
        pdf.set_x(lm)
        pdf.set_font("Helvetica", font, size)
        pdf.set_text_color(*color)
        try:
            pdf.multi_cell(0, h, _safe(_strip(text)),
                           new_x=XPos.LEFT, new_y=YPos.NEXT)
        except Exception as exc:
            logger.debug("PDF cell skipped (%s): %.60r", exc, text)
        finally:
            pdf.set_left_margin(M)
            pdf.set_x(M)

    pdf = FPDF(orientation="P", unit="mm", format=page_size)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_left_margin(M)
    pdf.set_right_margin(M)
    pdf.set_x(M)

    # Branded header
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(0, 6, f"Generated by Hipocampus · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
             align="R", new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.ln(6)

    lines   = content.split("\n")
    in_code = False
    code_buf: list[str] = []
    i = 0

    while i < len(lines):
        raw = lines[i].rstrip()

        # Always reset x at the top of each iteration
        pdf.set_left_margin(M)
        pdf.set_x(M)

        # Code fences
        if raw.startswith("```"):
            if in_code:
                in_code = False
                if code_buf:
                    try:
                        block = "\n".join(_safe(ln, 80) for ln in code_buf)
                        pdf.set_font("Courier", "", 9)
                        pdf.set_text_color(30, 30, 30)
                        pdf.set_fill_color(245, 245, 245)
                        pdf.set_draw_color(200, 200, 200)
                        pdf.multi_cell(0, 5, block, border=1, fill=True,
                                       new_x=XPos.LEFT, new_y=YPos.NEXT)
                    except Exception as exc:
                        logger.debug("Code block skipped: %s", exc)
                    code_buf = []
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(raw)
            i += 1
            continue

        # Table separator row — skip entirely
        stripped = raw.lstrip("|: -")
        if not stripped:
            i += 1
            continue

        # Headings
        if raw.startswith("# "):
            pdf.ln(4)
            cell(raw[2:], h=10, font="B", size=20)
            pdf.ln(2)

        elif raw.startswith("## "):
            pdf.ln(5)
            cell(raw[3:], h=8, font="B", size=15)
            try:
                pdf.set_draw_color(180, 180, 180)
                pdf.line(M, pdf.get_y(), pdf.w - M, pdf.get_y())
            except Exception:
                pass
            pdf.ln(3)

        elif raw.startswith("### "):
            pdf.ln(3)
            cell(raw[4:], h=7, font="B", size=12, color=(40, 40, 40))
            pdf.ln(1)

        elif raw.startswith("#### "):
            pdf.ln(2)
            cell(raw[5:], h=6, font="B", size=11, color=(60, 60, 60))

        # Bullet list
        elif raw.startswith("- ") or raw.startswith("* "):
            cell(f"-  {raw[2:]}", h=6, lm=M + IND)

        # Numbered list
        elif re.match(r"^\d+\. ", raw):
            m = re.match(r"^(\d+)\. (.*)", raw)
            num, txt = (m.group(1), m.group(2)) if m else ("*", raw)
            cell(f"{num}.  {txt}", h=6, lm=M + IND)

        # Markdown table row
        elif raw.startswith("|"):
            cells = [c.strip() for c in raw.strip("|").split("|")]
            row_text = "   ".join(cells)
            cell(row_text, h=6)

        # Horizontal rule
        elif raw.startswith("---") or raw.startswith("***"):
            pdf.ln(3)
            try:
                pdf.set_draw_color(180, 180, 180)
                pdf.line(M, pdf.get_y(), pdf.w - M, pdf.get_y())
            except Exception:
                pass
            pdf.ln(3)

        # Empty line
        elif not raw:
            pdf.ln(4)

        # Normal paragraph
        else:
            cell(raw, h=6)

        i += 1

    # Page footer
    pdf.set_y(-15)
    pdf.set_left_margin(M)
    pdf.set_x(M)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(160, 160, 160)
    try:
        pdf.cell(0, 10, f"Page {pdf.page_no()}", align="C")
    except Exception:
        pass

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=200,
    summary="Generate a document (MD / PDF / CSV)",
)
async def generate_document(
    body: GenerateRequest,
    current_user: UserOut = Depends(get_current_user),
) -> Response:
    """
    Generates a document using Qwen-Max and returns it as a downloadable file.

    The format determines the system prompt strategy:
      md/pdf — Qwen writes structured Markdown; pdf additionally converts
               the Markdown to a clean PDF using fpdf2.
      csv    — Qwen is constrained to return raw CSV with no wrappers.

    Parameters:
        body         (GenerateRequest) — {prompt, format, size}
        current_user (UserOut)         — authenticated user (auth-gated).

    Returns:
        Response — binary or text file with appropriate Content-Type and
                   Content-Disposition headers for in-browser download.

    Raises:
        HTTPException 500 — Qwen API or PDF rendering failure.
    """
    fmt    = body.format
    size   = body.size
    prompt = body.prompt.strip()

    logger.info(
        "Document generation: format=%s size=%s user=%s",
        fmt, size, current_user.id,
    )

    # ── Detect URLs in the prompt and pre-fetch their content ────────────
    # When the user shares a link (e.g. a financial report page), fetch it
    # so the AI has real data to work with instead of relying on training data.
    import re as _re
    urls = _re.findall(r"https?://\S+", prompt)
    url_context = ""
    if urls:
        logger.info("Fetching %d URL(s) from prompt for user %s", len(urls), current_user.id)
        fetched = []
        for url in urls[:2]:  # cap at 2 to keep prompt size reasonable
            content = await _fetch_url(url.rstrip(".,)\"'"))
            fetched.append(f"--- Content from {url} ---\n{content}\n")
        url_context = "\n\n".join(fetched)

    # Build the enriched prompt: URL content + original request
    enriched_prompt = prompt
    if url_context:
        enriched_prompt = (
            f"The user has provided the following source material from the web:\n\n"
            f"{url_context}\n\n"
            f"Using this real data, fulfil the following request:\n{prompt}"
        )

    # ── Decide whether web search is needed ──────────────────────────────
    # If the prompt already contains structured data (dollar amounts, Q1-Q4,
    # percentage figures, or 3+ numbers) the user has provided what we need.
    # Skip the search tool entirely so Qwen doesn't waste a round-trip looking
    # for logos or other irrelevant things that delay / break generation.
    INLINE_DATA_RE = re.compile(
        r'\$[\d,]+|Q[1-4]\s*[:=]|\d+(?:\.\d+)?\s*%|\b\d{3,}(?:,\d{3})+',
        re.IGNORECASE,
    )
    inline_hits = len(INLINE_DATA_RE.findall(prompt))
    # Use search only when: a URL was provided, OR no inline data was found
    # (meaning the user wants us to look up real-world current data).
    need_search = bool(urls) or inline_hits < 3

    system = _CSV_SYSTEM if fmt == "csv" else _DOC_SYSTEM

    try:
        if need_search:
            md_content, searched = await generate_with_search(
                system_prompt=system,
                messages=[{"role": "user", "content": enriched_prompt}],
                temperature=0.2 if fmt == "csv" else 0.4,
                max_tokens=4096,
            )
        else:
            # All data is inline — call plain generate() with no search tool
            # so Qwen cannot trigger a spurious search for logos/branding.
            md_content = await generate(
                system_prompt=system,
                messages=[{"role": "user", "content": enriched_prompt}],
                temperature=0.2 if fmt == "csv" else 0.4,
                max_tokens=4096,
            )
            searched = False

        logger.info(
            "Document generated: format=%s web_searched=%s need_search=%s user=%s",
            fmt, searched, need_search, current_user.id,
        )
    except Exception as exc:
        logger.error("Qwen generation error for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document generation failed — Qwen API error. Please try again.",
        )

    # ── Render and return ────────────────────────────────────────────────
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    if fmt == "md":
        return Response(
            content=md_content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition":
                    f'attachment; filename="hipocampus-{timestamp}.md"',
            },
        )

    if fmt == "csv":
        # Strip any accidental markdown wrapping Qwen might add
        csv_content = re.sub(r"^```(?:csv)?\n?", "", md_content).rstrip("`").strip()
        return Response(
            content=csv_content.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition":
                    f'attachment; filename="hipocampus-{timestamp}.csv"',
            },
        )

    if fmt == "pdf":
        try:
            pdf_bytes = _markdown_to_pdf(md_content, size)
        except Exception as exc:
            logger.error("PDF rendering error for user %s: %s", current_user.id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="PDF rendering failed. Try the MD format instead.",
            )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                    f'attachment; filename="hipocampus-{timestamp}.pdf"',
            },
        )

    # Unreachable — pydantic validates format above
    raise HTTPException(status_code=400, detail="Unsupported format.")