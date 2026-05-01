from __future__ import annotations

import io
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict

from backend.services.document_service import save_ocr_results, set_processing_step
from backend.services.gridfs_service import download_file_from_gridfs

logger = logging.getLogger(__name__)


async def process_document(document_id: str, gridfs_file_id: str, document_type: str) -> None:

    try:
        # 1. Download raw bytes from GridFS
        await set_processing_step(document_id, "Downloading file")
        file_data = await download_file_from_gridfs(gridfs_file_id)

        #2. Determine file extension from GridFS metadata (fall back to .bin)
        #We derive it from gridfs metadata; simpler: store extension in doc record.
        #For now we try to sniff from magic bytes.
        ext = _detect_extension(file_data)

        # Passport photos are face photographs — skip OCR, NER and validation
        # entirely.  There is nothing to read, match or verify.
        _PHOTO_TYPES = {"passport_photo", "passport photo", "passport photograph", "id photo"}
        if document_type.lower().strip() in _PHOTO_TYPES:
            logger.info("Document %s is a passport photo — skipping OCR and validation", document_id)
            from backend.database import db as _db
            from bson import ObjectId as _ObjId
            await _db.documents.update_one(
                {"_id": _ObjId(document_id)},
                {"$set": {
                    "status": "validated",
                    "processing_step": None,
                    "validation_result": {
                        "overall_valid": True,
                        "issues": [],
                        "skipped": True,
                        "skip_reason": "passport_photo",
                    },
                }},
            )
            return

        # 3. Write to a temp file so OCR functions can use a path
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name

        ocr_result: Dict[str, Any] = {}
        try:
            # 4. Run OCR
            await set_processing_step(document_id, "Running OCR")
            from backend.ocr_processor import (
                extract_text_by_document_type,
                extract_text_from_pdf,
                validate_ocr_result,
            )

            if ext == ".pdf":
                raw = extract_text_from_pdf(tmp_path)
                extracted_text = raw.get("text", "")
                ocr_meta = {
                    "page_count": raw.get("page_count"),
                    "has_embedded_text": raw.get("has_embedded_text"),
                }
                avg_conf = None
            else:
                raw = extract_text_by_document_type(tmp_path, document_type)
                extracted_text = raw.get("text", "")
                avg_conf = raw.get("average_confidence")
                ocr_meta = {
                    "config_used": raw.get("config_used"),
                    "average_confidence": avg_conf,
                }

            ocr_validation = validate_ocr_result(
                {"text": extracted_text, "average_confidence": avg_conf}
            )

            # 5. Run NER
            await set_processing_step(document_id, "Extracting fields")
            from backend.services.ner_service import (
                extract_document_specific_entities,
                extract_expiry_date,
            )

            entities = extract_document_specific_entities(extracted_text, document_type)
            expiry_info = extract_expiry_date(extracted_text, entities)

            # 6. Build confidence_scores summary
            confidence_scores: Dict[str, Any] = {}
            if avg_conf is not None:
                confidence_scores["ocr_average"] = avg_conf
            if not ocr_validation["is_valid"]:
                confidence_scores["ocr_issues"] = ocr_validation["issues"]

            # 7. Determine final processing status
            status = "processed"
            if ocr_validation.get("requires_manual_review"):
                status = "processed"  # still processed, just flagged

            ocr_result = {
                "status": status,
                "extracted_text": extracted_text,
                "extracted_entities": entities,
                "expiry_date": (
                    datetime.fromisoformat(expiry_info["expiry_date"])
                    if expiry_info.get("expiry_date")
                    else None
                ),
                "confidence_scores": confidence_scores,
                "ocr_metadata": ocr_meta,
            }

        except Exception as exc:
            logger.error("OCR/NER failed for document %s: %s", document_id, exc)
            ocr_result = {
                "status": "processing_failed",
                "extracted_text": None,
                "extracted_entities": {},
                "expiry_date": None,
                "confidence_scores": {},
                "ocr_metadata": {"error": str(exc)},
            }

        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        # 8. Persist OCR results
        await set_processing_step(document_id, "Saving OCR results")
        await save_ocr_results(document_id, ocr_result)
        logger.info("Document %s processed with status '%s'", document_id, ocr_result["status"])

        # 9. Validate document fields, dates and type against the application form.
        # Passport photo short-circuit is already handled above (early return).
        if ocr_result.get("status") == "processed":
            try:
                await set_processing_step(document_id, "Verifying document type")
                from backend.services.document_validation_service import (
                    validate_document_against_application,
                )
                # Step label is updated inside validate_document_against_application
                # via the HuggingFace service which runs type check + cross-check
                await set_processing_step(document_id, "Comparing dates")
                validation_result = await validate_document_against_application(document_id)
                logger.info("Document %s validation complete", document_id)

                # Set a meaningful final status based on validation outcome
                overall_valid = validation_result.get("overall_valid", True)
                final_status = "validated" if overall_valid else "validated_with_issues"
                from backend.database import db
                from bson import ObjectId
                await db.documents.update_one(
                    {"_id": ObjectId(document_id)},
                    {"$set": {"status": final_status, "processing_step": None}},
                )
            except Exception as val_exc:
                logger.warning(
                    "Post-OCR validation failed for document %s: %s",
                    document_id,
                    val_exc,
                )
                # Leave status as "processed" if validation itself errored

    except Exception as exc:
        logger.error("Background processing completely failed for document %s: %s", document_id, exc)
        # Mark as failed so the user doesn't see it stuck on "processing"
        try:
            await save_ocr_results(document_id, {
                "status": "processing_failed",
                "ocr_metadata": {"error": str(exc)},
            })
        except Exception:
            pass


async def revalidate_document(document_id: str) -> None:
    try:
        from backend.database import db
        from bson import ObjectId

        # Put the document back into a transient state so polling picks it up
        await db.documents.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"status": "processed", "processing_step": "Re-validating"}},
        )

        from backend.services.document_validation_service import (
            validate_document_against_application,
        )

        validation_result = await validate_document_against_application(document_id)
        overall_valid = validation_result.get("overall_valid", True)
        final_status = "validated" if overall_valid else "validated_with_issues"

        await db.documents.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"status": final_status, "processing_step": None}},
        )
        logger.info("Document %s re-validated → %s", document_id, final_status)
    except Exception as exc:
        logger.warning("Revalidation failed for document %s: %s", document_id, exc)


def _detect_extension(data: bytes) -> str:

    if data[:4] == b"%PDF":
        return ".pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] in (b"\xff\xd8",):
        return ".jpg"
    return ".bin"
