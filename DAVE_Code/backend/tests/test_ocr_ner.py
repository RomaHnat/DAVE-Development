"""
Tests for Sprints 5 & 6: OCR Processing, NLP Entity Extraction, and
Entity Validation.

All tests in this file are pure unit tests – no database or HTTP client
required.  They exercise the Python functions directly, which means they
run fast and work regardless of whether MongoDB is available.

Covers Sprint 5 (Enhanced OCR + NLP):
  - NER regex patterns: ID numbers, emails, phone numbers, dates
  - NER: extract_document_specific_entities
  - NER: extract_expiry_date
  - NER: extract_date_of_birth
  - OCR: validate_ocr_result (good text, short text, low confidence)
  - OCR: assess_image_quality (with a synthetic PNG, if Pillow is available)

Covers Sprint 6 (Entity Validation):
  - entity_validation_service.validate_extracted_entities (valid, missing, low conf)
  - entity_validation_service.check_data_consistency (mocked DB)
"""

import pytest
from unittest.mock import AsyncMock, patch

class TestExtractDocumentSpecificEntities:

    def test_extracts_email(self):
        from backend.services.ner_service import extract_document_specific_entities
        text = "Please contact john.doe@example.com for more information."
        result = extract_document_specific_entities(text, "default")
        emails = [e["value"] for e in result["emails"]]
        assert "john.doe@example.com" in emails

    def test_extracts_irish_phone(self):
        from backend.services.ner_service import extract_document_specific_entities
        # Use format that matches pattern: +353 or 0 followed by digits grouped correctly
        text = "Contact us at 0871234567 during office hours."
        result = extract_document_specific_entities(text, "default")
        phones = [p["value"] for p in result["phone_numbers"]]
        assert len(phones) >= 1

    def test_extracts_passport_number(self):
        from backend.services.ner_service import extract_document_specific_entities
        text = "Passport Number: AB1234567 issued by Irish authorities."
        result = extract_document_specific_entities(text, "passport")
        id_numbers = [i["value"] for i in result["id_numbers"]]
        assert "AB1234567" in id_numbers

    def test_extracts_pps_number(self):
        from backend.services.ner_service import extract_document_specific_entities
        text = "PPS Number: 1234567T"
        result = extract_document_specific_entities(text, "id_card")
        id_numbers = [i["value"] for i in result["id_numbers"]]
        assert "1234567T" in id_numbers

    def test_extracts_student_id(self):
        from backend.services.ner_service import extract_document_specific_entities
        text = "Student ID: T00228949 enrolled in Computing."
        result = extract_document_specific_entities(text, "default")
        id_numbers = [i["value"] for i in result["id_numbers"]]
        assert "T00228949" in id_numbers

    def test_extracts_date_dd_mm_yyyy(self):
        from backend.services.ner_service import extract_document_specific_entities
        text = "Date of issue: 15/06/2023"
        result = extract_document_specific_entities(text)
        dates = [d["value"] for d in result["dates"]]
        assert "15/06/2023" in dates

    def test_extracts_date_yyyy_mm_dd(self):
        from backend.services.ner_service import extract_document_specific_entities
        text = "Valid from 2023-01-01 until 2025-12-31."
        result = extract_document_specific_entities(text)
        dates = [d["value"] for d in result["dates"]]
        assert "2023-01-01" in dates
        assert "2025-12-31" in dates

    def test_no_false_positives_on_clean_text(self):
        from backend.services.ner_service import extract_document_specific_entities
        text = "This document contains no personal information whatsoever."
        result = extract_document_specific_entities(text)
        assert result["emails"] == []
        assert result["phone_numbers"] == []
        assert result["id_numbers"] == []

    def test_returns_all_entity_keys(self):
        from backend.services.ner_service import extract_document_specific_entities
        result = extract_document_specific_entities("hello world")
        expected_keys = {"names", "id_numbers", "dates", "emails", "phone_numbers", "addresses"}
        assert expected_keys.issubset(result.keys())


class TestExtractExpiryDate:

    def test_finds_expiry_after_keyword(self):
        from backend.services.ner_service import (
            extract_document_specific_entities,
            extract_expiry_date,
        )
        text = "Expiry: 31/12/2025"
        entities = extract_document_specific_entities(text)
        result = extract_expiry_date(text, entities)
        assert result["expiry_date_str"] == "31/12/2025"
        assert result["confidence"] > 0

    def test_finds_expiry_with_valid_until(self):
        from backend.services.ner_service import (
            extract_document_specific_entities,
            extract_expiry_date,
        )
        text = "Valid until 01/01/2030. Please renew before that date."
        entities = extract_document_specific_entities(text)
        result = extract_expiry_date(text, entities)
        assert result["expiry_date_str"] == "01/01/2030"

    def test_returns_none_when_no_expiry(self):
        from backend.services.ner_service import (
            extract_document_specific_entities,
            extract_expiry_date,
        )
        text = "This document has no expiry information."
        entities = extract_document_specific_entities(text)
        result = extract_expiry_date(text, entities)
        assert result["expiry_date"] is None
        assert result["confidence"] == 0.0


class TestExtractDateOfBirth:

    def test_finds_dob_after_keyword(self):
        from backend.services.ner_service import (
            extract_document_specific_entities,
            extract_date_of_birth,
        )
        text = "Date of birth: 10/05/1990"
        entities = extract_document_specific_entities(text)
        result = extract_date_of_birth(text, entities)
        # extract_date_of_birth returns an ISO date string or None
        assert result is not None
        assert "1990" in result

    def test_returns_none_when_no_dob(self):
        from backend.services.ner_service import (
            extract_document_specific_entities,
            extract_date_of_birth,
        )
        text = "No birth date found in this text."
        entities = extract_document_specific_entities(text)
        result = extract_date_of_birth(text, entities)
        assert result is None

class TestValidateOcrResult:

    def test_valid_result(self):
        from backend.ocr_processor import validate_ocr_result
        result = validate_ocr_result({"text": "John Smith DOB 01/01/1990", "average_confidence": 85.0})
        assert result["is_valid"] is True
        assert result["issues"] == []

    def test_text_too_short(self):
        from backend.ocr_processor import validate_ocr_result
        result = validate_ocr_result({"text": "Hi", "average_confidence": 90.0})
        assert result["is_valid"] is False
        assert any("short" in issue.lower() for issue in result["issues"])

    def test_low_confidence(self):
        from backend.ocr_processor import validate_ocr_result
        result = validate_ocr_result({"text": "Some reasonable length text here", "average_confidence": 20.0})
        assert result["is_valid"] is False
        assert any("confidence" in issue.lower() for issue in result["issues"])

    def test_high_special_char_ratio(self):
        from backend.ocr_processor import validate_ocr_result
        # Mostly garbage characters
        garbage = "!@#$%^&*!@#$%^&* !@#$%^&*!@#$%^"
        result = validate_ocr_result({"text": garbage, "average_confidence": 85.0})
        # Should flag either short text or high special char ratio
        assert result["is_valid"] is False

    def test_requires_manual_review_when_issues_present(self):
        from backend.ocr_processor import validate_ocr_result
        result = validate_ocr_result({"text": "x", "average_confidence": 10.0})
        assert result["requires_manual_review"] is True


class TestAssessImageQuality:

    def test_assess_valid_png(self):
        """assess_image_quality should return a dict with required keys for a valid PNG."""
        import struct, zlib
        from backend.ocr_processor import assess_image_quality

        # Build a minimal 1×1 white PNG
        def _chunk(name, data):
            crc = zlib.crc32(name + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        idat = zlib.compress(b"\x00\xff\xff\xff")
        png = (
            b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", idat)
            + _chunk(b"IEND", b"")
        )

        result = assess_image_quality(png)
        # The function should at minimum return a dict
        assert isinstance(result, dict)

    def test_assess_corrupt_bytes(self):
        """assess_image_quality should handle unreadable bytes gracefully."""
        from backend.ocr_processor import assess_image_quality
        result = assess_image_quality(b"\x00\x01\x02garbage")
        assert isinstance(result, dict)

class TestValidateExtractedEntities:

    def test_valid_entities_passport(self):
        from backend.services.entity_validation_service import validate_extracted_entities
        entities = {
            "names": [{"value": "Alice Smith", "confidence": 0.95}],
            "id_numbers": [{"value": "AB1234567", "confidence": 1.0}],
            "dates": [{"value": "01/01/2030", "confidence": 1.0}],
        }
        result = validate_extracted_entities(entities, doc_type="passport")
        assert result["is_valid"] is True
        assert result["issues"] == []

    def test_missing_required_entity_type(self):
        from backend.services.entity_validation_service import validate_extracted_entities
        # passport expects names, id_numbers, dates – we omit id_numbers
        entities = {
            "names": [{"value": "Alice Smith", "confidence": 0.95}],
            "id_numbers": [],   # empty
            "dates": [{"value": "01/01/2030", "confidence": 1.0}],
        }
        result = validate_extracted_entities(entities, doc_type="passport")
        assert result["is_valid"] is False
        assert any("id_numbers" in issue for issue in result["issues"])

    def test_low_confidence_generates_warning(self):
        from backend.services.entity_validation_service import validate_extracted_entities
        entities = {
            "names": [{"value": "Bob Jones", "confidence": 0.50}],  # below threshold
            "id_numbers": [{"value": "AB9876543", "confidence": 1.0}],
            "dates": [{"value": "31/12/2025", "confidence": 1.0}],
        }
        result = validate_extracted_entities(entities, doc_type="passport")
        # is_valid may be True (warnings don't fail), but warnings list should be non-empty
        assert len(result["warnings"]) >= 1

    def test_unknown_doc_type_uses_default(self):
        from backend.services.entity_validation_service import validate_extracted_entities
        entities = {
            "names": [{"value": "Unknown Person", "confidence": 0.9}],
        }
        # "unknown_type" falls back to default which only requires names
        result = validate_extracted_entities(entities, doc_type="unknown_type")
        assert result["is_valid"] is True

    def test_photo_doc_type_requires_nothing(self):
        from backend.services.entity_validation_service import validate_extracted_entities
        # "photo" has no expected entities
        result = validate_extracted_entities({}, doc_type="photo")
        assert result["is_valid"] is True
        assert result["issues"] == []


@pytest.mark.asyncio
async def test_check_data_consistency_invalid_id():
    from backend.services.entity_validation_service import check_data_consistency
    from unittest.mock import AsyncMock, patch

    # Patch db.documents.find so it never actually hits MongoDB
    with patch("backend.services.entity_validation_service.db") as mock_db:
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.documents.find.return_value = mock_cursor

        result = await check_data_consistency("not-a-valid-objectid")
        assert result["is_consistent"] is False


@pytest.mark.asyncio
async def test_check_data_consistency_no_documents():
    from backend.services.entity_validation_service import check_data_consistency
    from bson import ObjectId
    from unittest.mock import AsyncMock, patch

    app_id = str(ObjectId())
    with patch("backend.services.entity_validation_service.db") as mock_db:
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.documents.find.return_value = mock_cursor

        result = await check_data_consistency(app_id)
        assert result["is_consistent"] is True

class TestImagePreprocessing:

    @staticmethod
    def _make_png() -> bytes:
        import struct
        import zlib

        def _chunk(name: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(name + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        idat = zlib.compress(b"\x00\xff\xff\xff")
        return (
            b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", idat)
            + _chunk(b"IEND", b"")
        )

    def test_preprocess_image_always_returns_bytes(self):
        from backend.ocr_processor import preprocess_image

        result = preprocess_image(self._make_png())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_preprocess_image_passthrough_when_cv2_unavailable(self):
        from unittest.mock import patch

        from backend.ocr_processor import preprocess_image

        raw = self._make_png()
        with patch("backend.ocr_processor._CV2_AVAILABLE", False):
            result = preprocess_image(raw)
        assert result == raw

    def test_detect_skew_angle_returns_zero_when_cv2_unavailable(self):
        from unittest.mock import MagicMock, patch

        from backend.ocr_processor import detect_skew_angle

        with patch("backend.ocr_processor._CV2_AVAILABLE", False):
            result = detect_skew_angle(MagicMock())
        assert isinstance(result, float)
        assert result == 0.0

    def test_rotate_image_returns_input_when_cv2_unavailable(self):
        from unittest.mock import MagicMock, patch

        from backend.ocr_processor import rotate_image

        dummy = MagicMock()
        with patch("backend.ocr_processor._CV2_AVAILABLE", False):
            result = rotate_image(dummy, 45.0)
        assert result is dummy

    def test_enhance_contrast_returns_input_when_cv2_unavailable(self):
        from unittest.mock import MagicMock, patch

        from backend.ocr_processor import enhance_contrast

        dummy = MagicMock()
        with patch("backend.ocr_processor._CV2_AVAILABLE", False):
            result = enhance_contrast(dummy)
        assert result is dummy

    def test_preprocess_image_with_cv2_if_installed(self):
        pytest.importorskip("cv2")  # skip this test if opencv-python is not installed
        from backend.ocr_processor import preprocess_image

        result = preprocess_image(self._make_png())
        assert isinstance(result, bytes)
