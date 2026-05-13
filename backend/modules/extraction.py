"""
Multi-format text extraction.
Returns: list of (section_title: str | None, text: str)
"""
import json
import csv
import io
import logging
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)


def extract(file_path: str, file_type: str) -> list[tuple[str | None, str]]:
    """
    Dispatch to format-specific extractor.
    Returns list of (section, text) tuples.
    """
    ext = file_type.lower().lstrip(".")
    p = Path(file_path)

    try:
        if ext == "pdf":
            return _extract_pdf(p)
        elif ext == "docx":
            return _extract_docx(p)
        elif ext in ("html", "htm"):
            return _extract_html(p)
        elif ext in ("txt", "md"):
            return _extract_plain(p)
        elif ext == "csv":
            return _extract_csv(p)
        elif ext == "json":
            return _extract_json(p)
        else:
            return _extract_plain(p)
    except Exception as e:
        logger.error(f"Extraction failed for {file_path}: {e}")
        raise


def _extract_pdf(path: Path) -> list[tuple[str | None, str]]:
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    results: list[tuple[str | None, str]] = []

    for page_num, page in enumerate(doc):
        blocks = page.get_text("blocks")
        # blocks: (x0, y0, x1, y1, text, block_no, block_type)
        text_blocks = [b[4].strip() for b in blocks if b[6] == 0 and b[4].strip()]
        if text_blocks:
            results.append((f"Page {page_num + 1}", "\n".join(text_blocks)))

    doc.close()
    return results


def _extract_docx(path: Path) -> list[tuple[str | None, str]]:
    from docx import Document

    doc = Document(str(path))
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    buffer: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name.lower()
        if "heading" in style_name:
            if buffer:
                sections.append((current_heading, "\n".join(buffer)))
                buffer = []
            current_heading = text
        else:
            buffer.append(text)

    if buffer:
        sections.append((current_heading, "\n".join(buffer)))

    # Also extract tables
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            sections.append(("Table", "\n".join(rows)))

    return sections if sections else [(None, "")]


def _extract_html(path: Path) -> list[tuple[str | None, str]]:
    from bs4 import BeautifulSoup
    import chardet

    raw = path.read_bytes()
    enc = chardet.detect(raw)["encoding"] or "utf-8"
    html = raw.decode(enc, errors="replace")

    soup = BeautifulSoup(html, "lxml")

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    buffer: list[str] = []

    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "code"]):
        text = el.get_text(separator=" ", strip=True)
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            if buffer:
                sections.append((current_heading, "\n".join(buffer)))
                buffer = []
            current_heading = text
        else:
            buffer.append(text)

    if buffer:
        sections.append((current_heading, "\n".join(buffer)))

    return sections if sections else [(None, soup.get_text(separator="\n", strip=True))]


def _extract_plain(path: Path) -> list[tuple[str | None, str]]:
    import chardet

    raw = path.read_bytes()
    enc = chardet.detect(raw)["encoding"] or "utf-8"
    text = raw.decode(enc, errors="replace")
    return [(None, text)]


def _extract_csv(path: Path) -> list[tuple[str | None, str]]:
    import chardet

    raw = path.read_bytes()
    enc = chardet.detect(raw)["encoding"] or "utf-8"
    text = raw.decode(enc, errors="replace")

    reader = csv.reader(io.StringIO(text))
    rows = [" | ".join(row) for row in reader if any(cell.strip() for cell in row)]
    return [("CSV Data", "\n".join(rows))]


def _extract_json(path: Path) -> list[tuple[str | None, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        pretty = text
    return [("JSON Data", pretty)]