from __future__ import annotations

import io
from typing import Dict, List, Tuple

MAX_FILE_SIZE_MB: int = 10
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_FILES_PER_APPLICATION: int = 20

ALLOWED_EXTENSIONS: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

ALLOWED_MIME_TYPES: List[str] = list(set(ALLOWED_EXTENSIONS.values()))

# Human-readable label used in error messages
ALLOWED_FORMATS_LABEL: str = "PDF, JPG, JPEG, PNG"

def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def validate_file_type(filename: str, allowed_types: List[str] | None = None) -> bool:

    ext = _extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return False
    mime = ALLOWED_EXTENSIONS[ext]
    if allowed_types is not None:
        return mime in [t.lower() for t in allowed_types]
    return True


def validate_file_size(file_size: int, max_size_mb: int = MAX_FILE_SIZE_MB) -> bool:

    return file_size <= max_size_mb * 1024 * 1024


def validate_image(file_data: bytes) -> Dict:

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_data))
        img.verify()  # checks file integrity
        img = Image.open(io.BytesIO(file_data))  # re-open after verify
        return {
            "is_valid": True,
            "width": img.width,
            "height": img.height,
            "format": img.format,
        }
    except Exception as exc:
        return {"is_valid": False, "error": str(exc)}


def validate_pdf(file_data: bytes) -> Dict:

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_data, filetype="pdf")
        page_count = len(doc)
        has_text = any(
            bool(doc[i].get_text().strip()) for i in range(min(page_count, 3))
        )
        doc.close()
        return {"is_valid": page_count > 0, "page_count": page_count, "has_text": has_text}
    except Exception as exc:
        return {"is_valid": False, "error": str(exc)}


def validate_upload(
    filename: str,
    file_data: bytes,
    max_size_mb: int = MAX_FILE_SIZE_MB,
) -> Tuple[bool, List[str]]:

    errors: List[str] = []

    if not validate_file_type(filename):
        errors.append(
            f"File type not allowed. Accepted formats: {ALLOWED_FORMATS_LABEL}."
        )

    if not validate_file_size(len(file_data), max_size_mb):
        errors.append(f"File exceeds the {max_size_mb} MB size limit.")

    if not errors:
        ext = _extension(filename)
        if ext == ".pdf":
            result = validate_pdf(file_data)
            if not result.get("is_valid"):
                errors.append(
                    f"Invalid or corrupted PDF: {result.get('error', 'unknown error')}."
                )
        else:
            result = validate_image(file_data)
            if not result.get("is_valid"):
                errors.append(
                    f"Invalid or corrupted image: {result.get('error', 'unknown error')}."
                )

    return len(errors) == 0, errors
