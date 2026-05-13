"""
OCR pipeline for images and scanned PDFs.
Primary: Tesseract. Graceful fallback if unavailable.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
TESSERACT_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    import cv2
    import numpy as np
    TESSERACT_AVAILABLE = True
except ImportError:
    logger.warning("pytesseract/Pillow/cv2 not available — OCR disabled")


def run_ocr(file_path: str) -> str:
    """
    Extract text from image/scanned document.
    Returns empty string if OCR unavailable.
    """
    if not TESSERACT_AVAILABLE:
        return ""

    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _ocr_pdf(path)
    else:
        return _ocr_image(path)


def _preprocess_image(img_array: "np.ndarray") -> "np.ndarray":
    """Deskew, denoise, binarize for better OCR accuracy."""
    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array
    # Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    # Adaptive threshold (handles uneven lighting)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    return binary


def _ocr_image(path: Path) -> str:
    try:
        img = Image.open(str(path)).convert("RGB")
        arr = np.array(img)
        processed = _preprocess_image(arr)
        pil_img = Image.fromarray(processed)

        config = "--oem 3 --psm 3"  # LSTM engine, full auto page segmentation
        text = pytesseract.image_to_string(pil_img, config=config)
        return text.strip()
    except Exception as e:
        logger.error(f"OCR failed for {path}: {e}")
        return ""


def _ocr_pdf(path: Path) -> str:
    """OCR each page of a PDF as image."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        pages_text: list[str] = []

        for page in doc:
            # Render at 300 DPI
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")

            from io import BytesIO
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            arr = np.array(img)
            processed = _preprocess_image(arr)
            pil_img = Image.fromarray(processed)

            text = pytesseract.image_to_string(pil_img, config="--oem 3 --psm 3")
            if text.strip():
                pages_text.append(text.strip())

        doc.close()
        return "\n\n".join(pages_text)
    except Exception as e:
        logger.error(f"PDF OCR failed for {path}: {e}")
        return ""