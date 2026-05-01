from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from backend.database import db
from backend.services.document_classifier import (
    canonical_type,
    check_required_indicators,
    verify_against_requested,
)
from backend.services.name_matcher import (
    all_form_tokens_in_text,
    best_name_match,
    normalise_name,
)

logger = logging.getLogger(__name__)


def _is_name_issue(issue_text: str) -> bool:
    t = issue_text.lower()
    return (
        "extract a name" in t
        or "could not verify" in t
        or "name on document" in t
        or ("name" in t and "form name" in t and "does not match" in t)
        or "automatic name verification" in t
    )


def _parse_dob(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Prefer dateutil because it handles 50+ formats; fall back to a
    # narrow list of strict formats if it's missing.
    try:
        from dateutil import parser as _du_parser  # type: ignore

        return _du_parser.parse(text, dayfirst=True, fuzzy=True).date()
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
        "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _candidate_names(extracted_entities: Dict[str, Any]) -> List[str]:

    names: List[str] = []
    seen = set()
    for entry in extracted_entities.get("names", []) or []:
        if isinstance(entry, dict):
            value = entry.get("value")
        else:
            value = entry
        if not value:
            continue
        key = normalise_name(str(value))
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(str(value))
    return names


def validate_document_data(
    extracted_entities: Dict[str, Any],
    expiry_date: Optional[datetime],
    form_full_name: Optional[str],
    extracted_text: Optional[str] = None,
) -> Dict[str, Any]:
    
    result: Dict[str, Any] = {
        "name_match": None,
        "name_match_score": None,
        "expiry_valid": None,
        "is_expired": None,
        "overall_valid": True,
        "issues": [],
    }

    candidates = _candidate_names(extracted_entities)
    logger.info(
        "[NER layer] form_full_name=%r  candidate_names=%s",
        form_full_name,
        candidates,
    )

    if form_full_name:
        if candidates:
            best_candidate, score, matched = best_name_match(form_full_name, candidates)
            result["name_match_score"] = round(score, 3)
            logger.info(
                "[NER layer] best_name_match: candidate=%r  score=%.3f  matched=%s",
                best_candidate, score, matched,
            )
            if matched:
                result["name_match"] = True
            else:
                # Fall back to a fuzzy whole-text search before failing —
                # the form name might be in the document even if NER missed it.
                text_fallback = all_form_tokens_in_text(form_full_name, extracted_text) if extracted_text else False
                logger.info(
                    "[NER layer] Name match failed — trying OCR-text fuzzy fallback: "
                    "extracted_text_len=%d  all_form_tokens_in_text=%s",
                    len(extracted_text or ""), text_fallback,
                )
                if text_fallback:
                    result["name_match"] = True
                    result["name_match_score"] = max(score, 0.85)
                else:
                    result["name_match"] = False
                    result["overall_valid"] = False
                    # Only name the NER candidate in the error if it was a
                    # plausible near-miss (score >= 0.45 means the strings share
                    # substantial character overlap). A lower score means the
                    # candidate is OCR noise, not the applicant's real name —
                    # showing it would mislead the reviewer.
                    if best_candidate and score >= 0.45:
                        result["issues"].append(
                            f"Name on document ('{best_candidate}') does not match "
                            f"the application name ('{form_full_name}')."
                        )
                    else:
                        result["issues"].append(
                            "Could not verify the applicant's name on the document. "
                            "Please ensure the document is clearly legible and "
                            "belongs to the applicant."
                        )
        elif extracted_text and all_form_tokens_in_text(form_full_name, extracted_text):
            # NER pulled nothing but the form name is clearly in the text
            logger.info(
                "[NER layer] No NER candidates — OCR-text fuzzy fallback confirmed name %r in text",
                form_full_name,
            )
            result["name_match"] = True
            result["name_match_score"] = 0.85
        else:
            logger.warning(
                "[NER layer] No NER candidates AND OCR-text fallback failed. "
                "form_full_name=%r  extracted_text_len=%d  text_snippet=%r",
                form_full_name, len(extracted_text or ""), (extracted_text or "")[:300],
            )
            result["name_match"] = False
            result["overall_valid"] = False
            result["issues"].append(
                "Could not verify the name on the document against the application. "
                "Please ensure the document is clearly legible and belongs to the applicant."
            )
    elif candidates:
        result["issues"].append("Could not verify name: no full_name in application form.")

    if expiry_date is not None:
        now = datetime.now(timezone.utc)
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
        expired = expiry_date < now
        result["expiry_valid"] = not expired
        result["is_expired"] = expired
        if expired:
            result["overall_valid"] = False
            result["issues"].append(
                f"Document expired on {expiry_date.date().isoformat()}."
            )

    return result


async def validate_document_against_application(
    document_id: str,
    application_id: Optional[str] = None,
) -> Dict[str, Any]:
    doc = await db.documents.find_one({"_id": ObjectId(document_id)})
    if doc is None:
        return {"overall_valid": False, "issues": ["Document not found."]}

    app_oid = doc.get("application_id")
    if app_oid is None:
        return {"overall_valid": False, "issues": ["No application linked to document."]}

    app = await db.applications.find_one({"_id": app_oid})
    form_data: Dict[str, Any] = (app or {}).get("form_data") or {}
    form_full_name: Optional[str] = (
        form_data.get("full_name")
        or form_data.get("name")
        or form_data.get("applicant_name")
    )

    document_type = doc.get("document_type", "document")
    extracted_text = doc.get("extracted_text") or ""
    stored_entities = doc.get("extracted_entities") or {}

    # Passport photos are face photographs — there is no text to validate,
    # no name to match, and no expiry to check.  Skip all validation and
    # mark the document as valid immediately.
    _PHOTO_TYPES = {"passport_photo", "passport photo", "passport photograph", "id photo"}
    if canonical_type(document_type) == "passport_photo" or document_type.lower().strip() in _PHOTO_TYPES:
        logger.info(
            "[Validation] doc_id=%s  doc_type=%r — passport photo, skipping all validation",
            document_id, document_type,
        )
        photo_result = {"overall_valid": True, "issues": [], "skipped": True, "skip_reason": "passport_photo"}
        await db.documents.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"validation_result": photo_result}},
        )
        return photo_result

    logger.info(
        "[Validation] doc_id=%s  doc_type=%r  form_full_name=%r",
        document_id,
        document_type,
        form_full_name,
    )

    # Re-run NER if entities are missing — handles documents processed
    # before MRZ parsing or any later NER improvement was added.
    if not stored_entities.get("names") and extracted_text.strip():
        try:
            from backend.services.ner_service import extract_document_specific_entities

            refreshed = extract_document_specific_entities(extracted_text, document_type)
            if refreshed.get("names"):
                logger.info(
                    "[Validation] Refreshed NER found names: %s",
                    [n.get("value") for n in refreshed["names"]],
                )
                stored_entities = {**stored_entities, **refreshed}
                await db.documents.update_one(
                    {"_id": ObjectId(document_id)},
                    {"$set": {"extracted_entities": stored_entities}},
                )
        except Exception as ner_exc:
            logger.warning("[Validation] NER refresh failed: %s", ner_exc)

    validation_result = validate_document_data(
        extracted_entities=stored_entities,
        expiry_date=doc.get("expiry_date"),
        form_full_name=form_full_name,
        extracted_text=extracted_text,
    )

    logger.info(
        "[Validation] NER result: overall_valid=%s  issues=%s",
        validation_result.get("overall_valid"),
        validation_result.get("issues"),
    )

    # Offline keyword-based document type check — always runs, no API needed.
    classifier_result = verify_against_requested(extracted_text, document_type)
    validation_result["detected_type"] = classifier_result.get("detected_type")
    validation_result["detected_label"] = classifier_result.get("detected_label")
    validation_result["detected_confidence"] = classifier_result.get("confidence")

    if classifier_result.get("type_verified") is False:
        validation_result["overall_valid"] = False
        validation_result["issues"] = (validation_result.get("issues") or []) + [
            classifier_result["reason"]
        ]
    elif classifier_result.get("type_verified") is True:
        # Promote it into the HF type-verified slot too so the UI badge lights up.
        validation_result["hf_type_verified"] = True
        validation_result["hf_type_confidence"] = classifier_result.get("confidence")
        validation_result["hf_detected_as"] = classifier_result.get("detected_label")

    # Required-field check — runs for document types that have specific
    # content requirements (P60, enrolment letter, bank statement, travel
    # insurance).  Only runs when type_verified is not False so we don't
    # pile on a second set of issues when the document is already the
    # wrong type entirely.
    if classifier_result.get("type_verified") is not False:
        detected_canonical = classifier_result.get("detected_type") or canonical_type(document_type)
        if detected_canonical:
            field_issues = check_required_indicators(extracted_text, detected_canonical)
            if field_issues:
                validation_result["overall_valid"] = False
                validation_result["issues"] = (validation_result.get("issues") or []) + field_issues
                logger.info(
                    "[Validation] required_indicator issues for canonical=%r: %s",
                    detected_canonical, field_issues,
                )

    # Date-of-birth check (NER layer)
    form_dob_raw = form_data.get("date_of_birth") or form_data.get("dob")
    if form_dob_raw:
        try:
            from backend.services.ner_service import extract_date_of_birth as _ner_extract_dob

            doc_dob_str = _ner_extract_dob(extracted_text, doc.get("extracted_entities") or {})
        except Exception:
            doc_dob_str = None

        if doc_dob_str:
            doc_dob = _parse_dob(doc_dob_str)
            form_dob = _parse_dob(form_dob_raw)
            if doc_dob and form_dob and doc_dob != form_dob:
                validation_result["overall_valid"] = False
                validation_result["issues"] = (validation_result.get("issues") or []) + [
                    f"Date of birth on document ('{doc_dob.isoformat()}') does not match "
                    f"the application date of birth ('{form_dob.isoformat()}')."
                ]

    # Passport number check — runs when the form contains a passport_number
    # field (Visa Application) and the document being validated is a passport.
    # Compares the normalised form value against every passport-number-shaped
    # token in the OCR text and against MRZ line 2 position 0-9.
    form_passport_number: Optional[str] = form_data.get("passport_number")
    if form_passport_number and canonical_type(document_type) in ("passport", "id_card"):
        _pn_form = re.sub(r"[^A-Z0-9]", "", form_passport_number.upper())
        _pn_found = False
        if _pn_form:
            # Check raw OCR text — normalise both sides to uppercase alphanum
            _text_upper = re.sub(r"[^A-Z0-9]", "", extracted_text.upper())
            if _pn_form in _text_upper:
                _pn_found = True
                logger.info("[Validation] Passport number %r found in OCR text", _pn_form)
            # Check extracted id_numbers from NER
            if not _pn_found:
                for id_entry in (stored_entities.get("id_numbers") or []):
                    candidate = re.sub(r"[^A-Z0-9]", "", str(id_entry.get("value", "")).upper())
                    if candidate == _pn_form:
                        _pn_found = True
                        logger.info("[Validation] Passport number matched NER id_numbers entry %r", candidate)
                        break
            if not _pn_found:
                validation_result["overall_valid"] = False
                validation_result["issues"] = (validation_result.get("issues") or []) + [
                    f"Passport number on the form ('{form_passport_number}') was not found "
                    f"in the uploaded document. Please ensure the correct passport was uploaded."
                ]
                logger.info(
                    "[Validation] Passport number mismatch — form=%r not found in document",
                    _pn_form,
                )

    # HuggingFace cross-check (type + key field extraction). Optional —
    # the offline classifier above already covers type verification, so a
    # missing/failed HF call is not fatal.
    try:
        from backend.services.huggingface_service import analyse_document

        hf_result = await analyse_document(
            extracted_text=extracted_text,
            document_type=document_type,
            form_data=form_data,
        )
    except Exception as exc:
        logger.warning("[Validation] HF analysis raised: %s", exc)
        hf_result = None

    if hf_result:
        # Prefer the offline classifier's verdict when it's confident;
        # only fall back to HF when offline was inconclusive.
        if validation_result.get("hf_type_verified") is None:
            validation_result["hf_type_verified"] = hf_result.get("type_verified")
            validation_result["hf_type_confidence"] = hf_result.get("type_confidence")
            validation_result["hf_detected_as"] = hf_result.get("detected_as")

        validation_result["hf_extracted_fields"] = hf_result.get("extracted_fields") or {}
        validation_result["hf_field_confidences"] = hf_result.get("field_confidences") or {}

        # Cross-check (form vs document) — computed locally in HF service.
        # IMPORTANT: HF results are ADVISORY ONLY. The QA model
        # (deepset/roberta-base-squad2) is too noisy to be authoritative —
        # it can return wrong spans for "What is the employee name?" etc.,
        # which used to produce false-positive "Issue Found" alerts even
        # when the form data was 100% correct.
        # Authoritative validations are:
        #   - Name:        NER (with MRZ + fuzzy OCR-text fallback)
        #   - DOB:         NER + MRZ
        #   - Expiry:      NER (extract_expiry_date) on the stored doc
        #   - Doc type:    offline classifier (verify_against_requested)
        validation_result["ai_name_match"] = hf_result.get("ai_name_match")
        validation_result["ai_name_on_document"] = hf_result.get("ai_name_on_document")
        validation_result["ai_expiry_valid"] = hf_result.get("ai_expiry_valid")
        validation_result["ai_expiry_date_found"] = hf_result.get("ai_expiry_date_found")
        validation_result["ai_verified_fields"] = hf_result.get("ai_verified_fields") or {}
        validation_result["ai_inconsistencies"] = hf_result.get("ai_inconsistencies") or []
        validation_result["ai_summary"] = hf_result.get("ai_summary") or ""
        # NOTE: deliberately NOT propagating ai_overall_valid or
        # ai_inconsistencies into validation_result["overall_valid"] /
        # validation_result["issues"]. They remain visible to the UI as
        # advisory info but cannot fail validation on their own.

    # Final fuzzy text-search override.
    # Runs AFTER everything so it can clear name issues that earlier
    # layers raised when the form name is clearly present in the text.
    if (
        form_full_name
        and extracted_text
        and all_form_tokens_in_text(form_full_name, extracted_text)
    ):
        before = validation_result.get("issues") or []
        cleaned = [i for i in before if not _is_name_issue(i)]
        if len(cleaned) < len(before):
            logger.info(
                "[Validation] Fuzzy text-search confirmed %r in OCR — cleared %d name issue(s)",
                form_full_name,
                len(before) - len(cleaned),
            )
        validation_result["name_match"] = True
        validation_result["issues"] = cleaned
        if not cleaned:
            validation_result["overall_valid"] = True

    # Persist back to MongoDB
    await db.documents.update_one(
        {"_id": ObjectId(document_id)},
        {"$set": {"validation_result": validation_result}},
    )
    return validation_result
