"""
Text normalization pipeline.
Removes OCR artifacts, duplicated whitespace, page numbers, headers/footers.
"""
import re
import unicodedata


def clean_text(text: str) -> str:
    if not text:
        return ""

    # Unicode normalization (NFC)
    text = unicodedata.normalize("NFC", text)

    # Remove null bytes and control characters (keep \n \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Remove lone page numbers: lines that are only digits (possibly with whitespace)
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)

    # Remove repeated dashes/underscores used as separators
    text = re.sub(r"[-_=]{4,}", "", text)

    # Collapse excessive blank lines (>2 in a row → 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse horizontal whitespace
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)

    return text.strip()
