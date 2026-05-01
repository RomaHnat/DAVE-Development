import io
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import pytesseract
from PIL import Image

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

from backend.config.tesseract_config import (
    ACCEPTABLE_QUALITY_SCORE,
    BLUR_THRESHOLD,
    DEFAULT_MIN_CONFIDENCE,
    MAX_BRIGHTNESS,
    MAX_SPECIAL_CHAR_RATIO,
    MIN_BRIGHTNESS,
    MIN_CONTRAST,
    MIN_TEXT_LENGTH,
    TESSERACT_CONFIGS,
)

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\T00228949\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

def preprocess_image(image_data: bytes) -> bytes:

    if not _CV2_AVAILABLE:
        return image_data

    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return image_data

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2,
    )

    angle = detect_skew_angle(binary)
    deskewed = rotate_image(binary, angle) if abs(angle) > 0.5 else binary

    kernel = np.ones((1, 1), np.uint8)
    cleaned = cv2.morphologyEx(deskewed, cv2.MORPH_CLOSE, kernel)

    _, encoded = cv2.imencode(".png", cleaned)
    return encoded.tobytes()


def _upscale_if_small(img: "np.ndarray", min_dim: int = 1200) -> "np.ndarray":

    h, w = img.shape[:2]
    short = min(h, w)
    if short < min_dim:
        scale = min_dim / short
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    return img


def preprocess_image_light(image_data: bytes) -> bytes:

    if not _CV2_AVAILABLE:
        return image_data

    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return image_data

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = _upscale_if_small(gray)

    # CLAHE improves local contrast without binarizing
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    _, encoded = cv2.imencode(".png", enhanced)
    return encoded.tobytes()


def _run_ocr_bytes(image_bytes: bytes, config: str) -> tuple:

    try:
        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, config=config)
        data = pytesseract.image_to_data(
            image, config=config, output_type=pytesseract.Output.DICT
        )
        confs = [int(c) for c in data["conf"] if str(c) != "-1" and int(c) >= 0]
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        return text, round(avg_conf, 2)
    except Exception as exc:
        logger.warning("[OCR] _run_ocr_bytes failed config=%r: %s", config, exc)
        return "", 0.0


def detect_skew_angle(image: "np.ndarray") -> float:

    if not _CV2_AVAILABLE:
        return 0.0

    edges = cv2.Canny(image, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    if lines is None:
        return 0.0

    angles = []
    for rho, theta in lines[:, 0]:
        angle = (theta * 180 / np.pi) - 90
        angles.append(angle)
    return float(np.median(angles))


def rotate_image(image: "np.ndarray", angle: float) -> "np.ndarray":

    if not _CV2_AVAILABLE:
        return image

    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def enhance_contrast(image: "np.ndarray") -> "np.ndarray":

    if not _CV2_AVAILABLE:
        return image
    return cv2.equalizeHist(image)


def assess_image_quality(image_data: bytes) -> Dict[str, Any]:

    if not _CV2_AVAILABLE:
        return {
            "quality_score": 100,
            "is_acceptable": True,
            "issues": {},
            "recommendations": [],
            "note": "cv2 not installed – quality check skipped",
        }

    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"quality_score": 0, "is_acceptable": False,
                "issues": {"unreadable": True}, "recommendations": []}

    laplacian_var = float(cv2.Laplacian(img, cv2.CV_64F).var())
    brightness = float(np.mean(img))
    contrast = float(img.std())

    is_blurry = laplacian_var < BLUR_THRESHOLD
    is_too_dark = brightness < MIN_BRIGHTNESS
    is_too_bright = brightness > MAX_BRIGHTNESS
    is_low_contrast = contrast < MIN_CONTRAST

    quality_score = min(
        100,
        (0 if is_blurry else 30)
        + (0 if (is_too_dark or is_too_bright) else 30)
        + (0 if is_low_contrast else 40),
    )

    recommendations: List[str] = []
    if is_blurry:
        recommendations.append("Image is blurry – please retake with a steady hand.")
    if is_too_dark:
        recommendations.append("Image is too dark – improve lighting.")
    if is_too_bright:
        recommendations.append("Image is overexposed – reduce brightness.")
    if is_low_contrast:
        recommendations.append("Low contrast – use a plain background.")

    return {
        "quality_score": quality_score,
        "is_acceptable": quality_score >= ACCEPTABLE_QUALITY_SCORE,
        "issues": {
            "blurry": is_blurry,
            "too_dark": is_too_dark,
            "too_bright": is_too_bright,
            "low_contrast": is_low_contrast,
        },
        "recommendations": recommendations,
    }

def extract_text_from_image(image_data: bytes,
                             doc_type: Optional[str] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    config = TESSERACT_CONFIGS.get(doc_type or "default", TESSERACT_CONFIGS["default"])

    best_text = ""
    best_conf = 0.0

    # Attempt 1: aggressive preprocessing (good for clean flatbed scans)
    processed = preprocess_image(image_data)
    text1, conf1 = _run_ocr_bytes(processed, config)
    logger.info(
        "[OCR] extract_text_from_image attempt 1 (aggressive): "
        "text_len=%d  conf=%.1f%%  snippet=%r",
        len(text1.strip()), conf1, text1[:120],
    )
    if len(text1.strip()) > len(best_text.strip()):
        best_text, best_conf = text1, conf1

    # Attempt 2: light preprocessing – no binarization (better for phone photos)
    if len(best_text.strip()) < 150:
        light = preprocess_image_light(image_data)
        text2, conf2 = _run_ocr_bytes(light, config)
        logger.info(
            "[OCR] extract_text_from_image attempt 2 (light): "
            "text_len=%d  conf=%.1f%%  snippet=%r",
            len(text2.strip()), conf2, text2[:120],
        )
        if len(text2.strip()) > len(best_text.strip()):
            best_text, best_conf = text2, conf2

    # Attempt 3: raw bytes + PSM 11 (sparse text, last resort)
    if len(best_text.strip()) < 150:
        text3, conf3 = _run_ocr_bytes(image_data, "--oem 3 --psm 11")
        logger.info(
            "[OCR] extract_text_from_image attempt 3 (raw PSM 11): "
            "text_len=%d  conf=%.1f%%  snippet=%r",
            len(text3.strip()), conf3, text3[:120],
        )
        if len(text3.strip()) > len(best_text.strip()):
            best_text, best_conf = text3, conf3

    total_time = round(time.perf_counter() - t0, 4)
    return {
        "text": best_text,
        "average_confidence": round(best_conf, 2),
        "metrics": {
            "total_time": total_time,
            "character_count": len(best_text),
        },
    }


def extract_text_by_document_type(image_path: str, doc_type: str) -> Dict[str, Any]:

    image_path = str(image_path)
    config = TESSERACT_CONFIGS.get(doc_type, TESSERACT_CONFIGS["default"])

    with open(image_path, "rb") as fh:
        raw = fh.read()

    best_text = ""
    best_conf = 0.0
    used_config = config

    #Attempt 1: aggressive preprocessing
    processed = preprocess_image(raw)
    text1, conf1 = _run_ocr_bytes(processed, config)
    logger.info(
        "[OCR] Attempt 1 (aggressive preprocess + config=%r): "
        "text_len=%d  conf=%.1f%%  snippet=%r",
        config, len(text1.strip()), conf1, text1[:120],
    )
    if len(text1.strip()) > len(best_text.strip()):
        best_text, best_conf = text1, conf1

    #Attempt 2: light preprocessing (no binarization)
    if len(best_text.strip()) < 150:
        light = preprocess_image_light(raw)
        text2, conf2 = _run_ocr_bytes(light, config)
        logger.info(
            "[OCR] Attempt 2 (light preprocess + config=%r): "
            "text_len=%d  conf=%.1f%%  snippet=%r",
            config, len(text2.strip()), conf2, text2[:120],
        )
        if len(text2.strip()) > len(best_text.strip()):
            best_text, best_conf = text2, conf2
            used_config = config

    #Attempt 3: raw bytes + PSM 11 (sparse text)
    if len(best_text.strip()) < 150:
        sparse_config = "--oem 3 --psm 11"
        text3, conf3 = _run_ocr_bytes(raw, sparse_config)
        logger.info(
            "[OCR] Attempt 3 (raw + PSM 11): "
            "text_len=%d  conf=%.1f%%  snippet=%r",
            len(text3.strip()), conf3, text3[:120],
        )
        if len(text3.strip()) > len(best_text.strip()):
            best_text, best_conf = text3, conf3
            used_config = sparse_config

    logger.info(
        "[OCR] Final: text_len=%d  conf=%.1f%%  config=%r\nFull text (first 800 chars):\n%s",
        len(best_text.strip()), best_conf, used_config, best_text[:800],
    )

    return {
        "text": best_text,
        "average_confidence": round(best_conf, 2),
        "config_used": used_config,
        "document_type": doc_type,
    }


def validate_ocr_result(result: Dict[str, Any]) -> Dict[str, Any]:

    text = result.get("text", "")
    avg_conf = result.get("average_confidence")

    issues: List[str] = []

    if len(text.strip()) < MIN_TEXT_LENGTH:
        issues.append("Extracted text is too short – OCR may have failed.")

    # Confidence is only meaningful when OCR actually ran. PDFs with
    # embedded text bypass tesseract and report avg_conf=None.
    if avg_conf is not None and avg_conf < 50:
        issues.append(f"Low average confidence score: {avg_conf:.1f}%.")

    if text:
        special_char_ratio = sum(
            not c.isalnum() and not c.isspace() for c in text
        ) / len(text)
        if special_char_ratio > MAX_SPECIAL_CHAR_RATIO:
            issues.append(
                f"High special-character ratio ({special_char_ratio:.0%}) "
                "– possible gibberish output."
            )

    return {
        "is_valid": len(issues) == 0,
        "issues": issues,
        "requires_manual_review": len(issues) > 0,
    }

def _is_meaningful_text(text: str, min_alpha_ratio: float = 0.40, min_length: int = 50) -> bool:

    stripped = text.strip()
    if len(stripped) < min_length:
        return False
    alpha = sum(1 for c in stripped if c.isalpha())
    return (alpha / len(stripped)) >= min_alpha_ratio


def extract_text_from_pdf(pdf_path: str) -> Dict[str, Any]:

    if not _FITZ_AVAILABLE:
        raise RuntimeError(
            "PyMuPDF (fitz) is not installed. "
            'Run: pip install "pymupdf==1.23.8"'
        )

    doc = fitz.open(pdf_path)
    page_count = len(doc)
    all_text: List[str] = []
    has_embedded_text = False

    for page in doc:
        page_text = page.get_text()
        if _is_meaningful_text(page_text):
            # PDF has a good embedded text layer — use it directly
            has_embedded_text = True
            all_text.append(page_text)
            logger.info(
                "[OCR] PDF page %d: using embedded text (%d chars)",
                page.number, len(page_text.strip()),
            )
        else:
            # Embedded text is absent or garbage — rasterise and run OCR
            if page_text.strip():
                logger.warning(
                    "[OCR] PDF page %d: embedded text present but too short/garbled "
                    "(%d chars: %r) — discarding and running Tesseract instead",
                    page.number, len(page_text.strip()), page_text[:120],
                )
            else:
                logger.info(
                    "[OCR] PDF page %d: no embedded text — rasterising for OCR",
                    page.number,
                )
            # Rasterise at 2× resolution for better OCR quality
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_bytes = pix.tobytes("png")
            result = extract_text_from_image(img_bytes)
            all_text.append(result["text"])

    doc.close()
    return {
        "text": "\n\n--- Page Break ---\n\n".join(all_text),
        "page_count": page_count,
        "has_embedded_text": has_embedded_text,
    }

