from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import openai as _openai_module  # type: ignore
    _OPENAI_AVAILABLE = True
except ImportError:
    _openai_module = None  # type: ignore
    _OPENAI_AVAILABLE = False

_PII_FIELDS = {
    "full_name", "name", "first_name", "last_name", "applicant_name",
    "date_of_birth", "dob", "birth_date",
    "pps_number", "ppsn", "social_security",
    "passport_number", "id_number", "national_id",
    "phone", "phone_number", "mobile", "telephone",
    "email", "email_address",
    "address", "street_address", "home_address",
    "bank_account", "iban", "sort_code",
}


def _strip_pii(form_data: Dict[str, Any]) -> Dict[str, Any]:

    return {k: v for k, v in form_data.items() if k.lower() not in _PII_FIELDS}


_SYSTEM_PROMPT = """You are a document requirements advisor for DAVE, an Irish
digital application verification system. When given the name of an application
type and the applicant's form data you MUST respond with a valid JSON array.

Each element of the array describes one recommended supporting document:
{
  "document_type": "<concise document name>",
  "reason": "<one sentence explaining why this document is needed>",
  "is_mandatory": <true | false>,
  "condition": "<optional — the form-field condition that triggers this requirement, e.g. marital_status == Married>"
}

Rules:
- Only suggest documents that are directly relevant to the form data provided.
- Do not repeat documents that are already listed in already_required.
- Focus on Irish legal and administrative requirements.
- Return an empty array [] if no additional documents are needed.
- Return ONLY the JSON array — no markdown fences, no explanatory text.
"""


def _build_user_message(
    application_type_name: str,
    form_data: Dict[str, Any],
    already_required: List[str],
) -> str:
    lines = [
        f"Application type: {application_type_name}",
        "",
        "Form data submitted by the applicant:",
    ]
    for k, v in form_data.items():
        lines.append(f"  {k}: {v}")

    if already_required:
        lines.append("")
        lines.append("Documents already configured as required (do NOT repeat these):")
        for doc in already_required:
            lines.append(f"  - {doc}")

    lines.append("")
    lines.append(
        "Based on the form data above, list any ADDITIONAL supporting documents "
        "the applicant should be asked to provide. Return a JSON array."
    )
    return "\n".join(lines)


async def suggest_required_documents(
    application_type_name: str,
    form_data: Dict[str, Any],
    already_required: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not _OPENAI_AVAILABLE:
        logger.debug(
            "OpenAI suggestions skipped: OPENAI_API_KEY not set or openai package missing."
        )
        return []

    already = already_required or []
    # Strip all PII before sending to OpenAI — names, DOB, IDs, etc. are
    # handled exclusively by the HuggingFace service (stays on our API key).
    safe_form_data = _strip_pii(form_data)
    user_msg = _build_user_message(application_type_name, safe_form_data, already)

    try:
        client = _openai_module.AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        raw = response.choices[0].message.content or "[]"
        suggestions: List[Dict[str, Any]] = json.loads(raw)
        if not isinstance(suggestions, list):
            return []
        # Sanitise each entry
        cleaned = []
        for item in suggestions:
            if not isinstance(item, dict):
                continue
            cleaned.append(
                {
                    "document_type": str(item.get("document_type", "Unknown")),
                    "reason": str(item.get("reason", "")),
                    "is_mandatory": bool(item.get("is_mandatory", False)),
                    "condition": item.get("condition") or None,
                }
            )
        return cleaned

    except json.JSONDecodeError as exc:
        logger.warning("OpenAI returned non-JSON response: %s", exc)
        return []
    except Exception as exc:
        logger.error("OpenAI API call failed: %s", exc)
        return []

_VALIDATION_SYSTEM_PROMPT = """\
You are a document verification assistant for DAVE, an Irish digital application system.
You will be given OCR-extracted text from a supporting document and the applicant's form data.
Your job is to cross-check the document against the form.

You MUST respond with a single valid JSON object ONLY — no markdown fences, no extra text.
Use exactly this structure:
{{
  "name_match": true | false | null,
  "name_on_document": "<exact name found on the document, or null>",
  "expiry_valid": true | false | null,
  "expiry_date_found": "<YYYY-MM-DD if found on document, else null>",
  "verified_fields": {{"<form_field_name>": "<matching value found on document>"}},
  "inconsistencies": ["<describe each clear mismatch between form data and document>"],
  "overall_valid": true | false,
  "ai_summary": "<one sentence summary of the verification result>"
}}

Rules:
- Compare today's date (provided below) to decide if the document is expired.
- name_match: compare the name on the document to the applicant's full_name. Set null if no name found.
- verified_fields: only include fields you can clearly read on the document (e.g. date_of_birth, ppsn, id_number, address).
- inconsistencies: list ONLY definite mismatches. Be lenient with minor formatting differences (e.g. "John O'Brien" vs "John OBrien").
- overall_valid: false if name_match is false OR if expiry_valid is false OR if there are inconsistencies.
"""


def _build_validation_user_message(
    extracted_text: str,
    form_data: Dict[str, Any],
    document_type: str,
    today: str,
) -> str:
    lines = [
        f"Today's date: {today}",
        f"Document type: {document_type}",
        "",
        "--- APPLICANT FORM DATA ---",
    ]
    for k, v in form_data.items():
        lines.append(f"  {k}: {v}")

    lines += [
        "",
        "--- OCR-EXTRACTED DOCUMENT TEXT ---",
        extracted_text.strip()[:4000],  # cap to avoid token overflow
        "",
        "Verify the document against the form data and return the JSON object.",
    ]
    return "\n".join(lines)


async def validate_document_with_ai(
    extracted_text: str,
    form_data: Dict[str, Any],
    document_type: str = "document",
) -> Optional[Dict[str, Any]]:
    logger.debug(
        "validate_document_with_ai: disabled for privacy — use huggingface_service.analyse_document instead."
    )
    return None
    #dead code kept for reference
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not _OPENAI_AVAILABLE:
        logger.debug("AI document validation skipped: OPENAI_API_KEY not set or openai package missing.")
        return None

    if not extracted_text or not extracted_text.strip():
        logger.debug("AI document validation skipped: no extracted text.")
        return None

    today = date.today().isoformat()
    user_msg = _build_validation_user_message(extracted_text, form_data, document_type, today)

    try:
        client = _openai_module.AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _VALIDATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=600,
        )
        raw = (response.choices[0].message.content or "").strip()
        result: Dict[str, Any] = json.loads(raw)

        # Sanitise / normalise fields
        return {
            "name_match": result.get("name_match"),
            "name_on_document": result.get("name_on_document") or None,
            "expiry_valid": result.get("expiry_valid"),
            "expiry_date_found": result.get("expiry_date_found") or None,
            "verified_fields": result.get("verified_fields") or {},
            "inconsistencies": result.get("inconsistencies") or [],
            "overall_valid": bool(result.get("overall_valid", True)),
            "ai_summary": result.get("ai_summary") or "",
        }

    except json.JSONDecodeError as exc:
        logger.warning("AI validation returned non-JSON: %s", exc)
        return None
    except Exception as exc:
        logger.error("AI document validation failed: %s", exc)
        return None
