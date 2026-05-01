"""
Tesseract OCR configuration profiles for different document types.

OEM (OCR Engine Mode):
  0 = Original Tesseract only
  1 = Neural nets LSTM only
  2 = Tesseract + LSTM
  3 = Default (best available)

PSM (Page Segmentation Mode):
  3  = Fully automatic page segmentation (default)
  4  = Assume a single column of text of variable sizes
  6  = Assume a single uniform block of text
  11 = Sparse text – find as much text as possible in no particular order
"""

TESSERACT_CONFIGS: dict[str, str] = {
    "default": "--oem 3 --psm 3",
    "id_card": "--oem 3 --psm 6",
    "passport": "--oem 3 --psm 6",
    "certificate": "--oem 3 --psm 4",
    "form": "--oem 3 --psm 6",
    "bank_statement": "--oem 3 --psm 3",
    "travel_insurance": "--oem 3 --psm 3",
    "utility_bill": "--oem 3 --psm 4",
    "photo": "--oem 3 --psm 11",
}

# Minimum confidence threshold for a word to be included in high-confidence output
DEFAULT_MIN_CONFIDENCE: int = 60

# Minimum text length to consider OCR result valid
MIN_TEXT_LENGTH: int = 20

# Maximum ratio of special characters before result is flagged as gibberish
MAX_SPECIAL_CHAR_RATIO: float = 0.30

# Image quality thresholds
BLUR_THRESHOLD: float = 100.0          # Laplacian variance below this → blurry
MIN_BRIGHTNESS: int = 50               # Mean pixel value below this → too dark
MAX_BRIGHTNESS: int = 200              # Mean pixel value above this → too bright
MIN_CONTRAST: float = 30.0             # Pixel std-dev below this → low contrast
ACCEPTABLE_QUALITY_SCORE: int = 60     # Quality score (0-100) required to skip warning
