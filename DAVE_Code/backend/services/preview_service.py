from __future__ import annotations

import io
from typing import Tuple

_DEFAULT_MAX_SIZE: Tuple[int, int] = (400, 400)  # pixels
_PDF_DPI_SCALE: float = 1.5  # ~108 DPI for readable thumbnail


def generate_pdf_thumbnail(pdf_data: bytes) -> bytes:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_data, filetype="pdf")
    if len(doc) == 0:
        doc.close()
        raise ValueError("PDF has no pages")

    page = doc[0]
    matrix = fitz.Matrix(_PDF_DPI_SCALE, _PDF_DPI_SCALE)
    pix = page.get_pixmap(matrix=matrix)
    doc.close()

    png_bytes = pix.tobytes("png")
    return resize_image(png_bytes, _DEFAULT_MAX_SIZE)


def generate_image_thumbnail(image_data: bytes) -> bytes:
    return resize_image(image_data, _DEFAULT_MAX_SIZE)


def resize_image(image_data: bytes, max_size: Tuple[int, int] = _DEFAULT_MAX_SIZE) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(image_data))

    # Convert palette / RGBA to RGB for JPEG compatibility if needed
    if img.mode in ("P", "RGBA"):
        img = img.convert("RGBA")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    img.thumbnail(max_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
