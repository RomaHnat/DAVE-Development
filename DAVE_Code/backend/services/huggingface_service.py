from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.services.document_classifier import canonical_type
from backend.services.name_matcher import best_name_match

logger = logging.getLogger(__name__)

_HF_API_BASE = "https://router.huggingface.co/hf-inference/models"
_CLASSIFICATION_MODEL = "facebook/bart-large-mnli"
_QA_MODEL = "deepset/roberta-base-squad2"

_ALL_LABELS: List[str] = [
    "P60 end of year tax certificate",
    "student enrollment or enrolment letter",
    "passport or travel document",
    "national identity card",
    "birth certificate",
    "marriage certificate",
    "bank statement",
    "utility bill",
    "payslip or salary slip",
    "proof of address",
    "driving licence",
    "travel insurance policy",
    "personal statement essay",
    "academic transcript or educational certificate",
    "reference or recommendation letter",
    "passport-style identity photo",
    "other unrelated document",
]

# Canonical key (from document_classifier) → HF label
_CANONICAL_TO_LABEL: Dict[str, str] = {
    "p60":                       "P60 end of year tax certificate",
    "enrollment_letter":         "student enrollment or enrolment letter",
    "passport":                  "passport or travel document",
    "id_card":                   "national identity card",
    "birth_certificate":         "birth certificate",
    "marriage_certificate":      "marriage certificate",
    "bank_statement":            "bank statement",
    "utility_bill":              "utility bill",
    "payslip":                   "payslip or salary slip",
    "driving_licence":           "driving licence",
    "travel_insurance":          "travel insurance policy",
    "personal_statement":        "personal statement essay",
    "educational_certificate":   "academic transcript or educational certificate",
    "reference_letter":          "reference or recommendation letter",
    "passport_photo":            "passport-style identity photo",
}


def _label_for_type(document_type: str) -> Optional[str]:
    canonical = canonical_type(document_type)
    if not canonical:
        return None
    return _CANONICAL_TO_LABEL.get(canonical)

_FIELD_QUESTIONS: Dict[str, List[Tuple[str, str]]] = {
    "p60": [
        ("employee_name",   "What is the employee name?"),
        ("employer_name",   "What is the employer name?"),
        ("tax_year",        "What is the tax year?"),
        ("total_pay",       "What is the total pay or gross pay?"),
        ("total_tax",       "What is the total income tax deducted?"),
    ],
    "enrollment letter": [
        ("student_name",    "What is the student name?"),
        ("institution",     "What is the college or university name?"),
        ("course_name",     "What is the course or programme name?"),
        ("academic_year",   "What is the academic year?"),
    ],
    "enrolment letter": [
        ("student_name",    "What is the student name?"),
        ("institution",     "What is the college or university name?"),
        ("course_name",     "What is the course or programme name?"),
        ("academic_year",   "What is the academic year?"),
    ],
    "student enrollment letter": [
        ("student_name",    "What is the student name?"),
        ("institution",     "What is the college or university name?"),
        ("course_name",     "What is the course or programme name?"),
        ("academic_year",   "What is the academic year?"),
    ],
    "student enrolment letter": [
        ("student_name",    "What is the student name?"),
        ("institution",     "What is the college or university name?"),
        ("course_name",     "What is the course or programme name?"),
        ("academic_year",   "What is the academic year?"),
    ],
    "passport": [
        ("full_name",           "What is the full name?"),
        ("date_of_birth",       "What is the date of birth?"),
        ("nationality",         "What is the nationality?"),
        ("passport_number",     "What is the passport number?"),
        ("expiry_date",         "What is the expiry date?"),
    ],
    "birth certificate": [
        ("full_name",       "What is the name on the birth certificate?"),
        ("date_of_birth",   "What is the date of birth?"),
        ("place_of_birth",  "What is the place of birth?"),
    ],
    "marriage certificate": [
        ("person1_name",        "What is the name of the first person getting married?"),
        ("person2_name",        "What is the name of the second person getting married?"),
        ("date_of_marriage",    "What is the date of the marriage?"),
        ("place_of_marriage",   "Where did the marriage take place?"),
    ],
    "bank statement": [
        ("account_holder",      "What is the account holder name?"),
        ("bank_name",           "What is the bank name?"),
        ("account_number",      "What is the account number?"),
        ("statement_period",    "What is the statement period or date range?"),
    ],
    "payslip": [
        ("employee_name",   "What is the employee name?"),
        ("employer_name",   "What is the employer or company name?"),
        ("pay_period",      "What is the pay period or pay date?"),
        ("gross_pay",       "What is the gross pay amount?"),
    ],
    "utility bill": [
        ("account_holder",  "What is the account holder name?"),
        ("provider",        "What is the utility provider name?"),
        ("address",         "What is the service address?"),
        ("bill_date",       "What is the bill date?"),
    ],
    "proof of address": [
        ("name",        "What is the name on the document?"),
        ("address",     "What is the address?"),
        ("date",        "What is the date of the document?"),
    ],
}

def _get_api_key() -> Optional[str]:
    key = os.getenv("HUGGINGFACE_API_KEY", "").strip()
    return key or None


async def _hf_post(
    client: httpx.AsyncClient,
    model: str,
    payload: dict,
) -> Optional[dict]:
    api_key = _get_api_key()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{_HF_API_BASE}/{model}"
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
        # 503 means the model is loading on HF servers; wait and retry once
        if resp.status_code == 503:
            logger.info("HuggingFace model '%s' is loading, retrying in 10s…", model)
            await asyncio.sleep(10)
            resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            logger.warning(
                "HuggingFace API %s error %s: %s",
                model, resp.status_code, resp.text[:200],
            )
            return None
        return resp.json()
    except Exception as exc:
        logger.warning("HuggingFace request failed for %s: %s", model, exc)
        return None
    
async def verify_document_type(
    extracted_text: str,
    claimed_type: str,
) -> Dict[str, Any]:

    empty: Dict[str, Any] = {
        "type_verified": None,
        "type_confidence": None,
        "detected_as": None,
    }
    if not _get_api_key() or not extracted_text.strip():
        return empty

    expected_label = _label_for_type(claimed_type)
    text_snippet = extracted_text.strip()[:2000]

    async with httpx.AsyncClient() as client:
        result = await _hf_post(client, _CLASSIFICATION_MODEL, {
            "inputs": text_snippet,
            "parameters": {"candidate_labels": _ALL_LABELS},
        })

    if not result or "labels" not in result:
        return empty

    top_label: str = result["labels"][0]
    top_score: float = float(result["scores"][0])

    if expected_label is None:
        return {
            "type_verified": None,
            "type_confidence": round(top_score, 4),
            "detected_as": top_label,
        }

    # Verified when the expected label scored highest with reasonable confidence,
    # OR when the expected label is in the top 2 with a small lead by the runner-up.
    verified = (top_label == expected_label) and (top_score >= 0.55)
    if not verified and len(result["labels"]) >= 2:
        runner_label = result["labels"][1]
        runner_score = float(result["scores"][1])
        if runner_label == expected_label and (top_score - runner_score) < 0.10:
            verified = True
    return {
        "type_verified": verified,
        "type_confidence": round(top_score, 4),
        "detected_as": top_label,
    }


async def extract_key_fields(
    extracted_text: str,
    document_type: str,
) -> Dict[str, Any]:

    empty: Dict[str, Any] = {"extracted_fields": {}, "field_confidences": {}}
    if not _get_api_key() or not extracted_text.strip():
        return empty

    questions = _FIELD_QUESTIONS.get(document_type.lower().strip(), [])
    if not questions:
        return empty

    context = extracted_text.strip()[:3000]

    async with httpx.AsyncClient() as client:
        tasks = [
            _hf_post(client, _QA_MODEL, {
                "inputs": {"question": question, "context": context},
            })
            for _, question in questions
        ]
        results = await asyncio.gather(*tasks)

    # roberta-base-squad2 is very noisy at low confidence — it will happily
    # return a span for any question. We require a meaningful score to avoid
    # feeding garbage into the cross-check (which used to flip overall_valid
    # to False on a single bad QA answer).
    extracted_fields: Dict[str, Any] = {}
    field_confidences: Dict[str, float] = {}
    for (field_name, _), result in zip(questions, results):
        if result and float(result.get("score", 0)) >= 0.35:
            answer = (result.get("answer") or "").strip()
            if not answer:
                continue
            extracted_fields[field_name] = answer
            field_confidences[field_name] = round(float(result.get("score", 0)), 4)

    return {
        "extracted_fields": extracted_fields,
        "field_confidences": field_confidences,
    }


async def analyse_document(
    extracted_text: str,
    document_type: str,
    form_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:

    if not _get_api_key():
        logger.debug("HuggingFace analysis skipped: HUGGINGFACE_API_KEY not set.")
        return None

    if not extracted_text or not extracted_text.strip():
        logger.debug("HuggingFace analysis skipped: no extracted text.")
        return None

    try:
        type_result, fields_result = await asyncio.gather(
            verify_document_type(extracted_text, document_type),
            extract_key_fields(extracted_text, document_type),
        )
        logger.info(
            "[HF] type_result=%s  extracted_fields=%s",
            type_result,
            fields_result.get("extracted_fields"),
        )
        cross_result = cross_check_document_vs_form(
            extracted_fields=fields_result.get("extracted_fields", {}),
            form_data=form_data or {},
            document_type=document_type,
        )
        logger.info(
            "[HF] cross_check: ai_name_match=%s  ai_name_on_document=%r  inconsistencies=%s",
            cross_result.get("ai_name_match"),
            cross_result.get("ai_name_on_document"),
            cross_result.get("ai_inconsistencies"),
        )
        return {**type_result, **fields_result, **cross_result}
    except Exception as exc:
        logger.error("HuggingFace document analysis failed: %s", exc)
        return None

# Document field names the QA model returns → form field names to compare against
_FIELD_TO_FORM_MAP: Dict[str, List[str]] = {
    "full_name":        ["full_name", "name", "applicant_name"],
    "employee_name":    ["full_name", "name", "applicant_name"],
    "student_name":     ["full_name", "name", "applicant_name"],
    "account_holder":   ["full_name", "name", "applicant_name"],
    "name":             ["full_name", "name", "applicant_name"],
    "person1_name":     ["full_name", "name", "applicant_name"],
    "person2_name":     ["spouse_name", "partner_name"],
    "course_name":      ["course_name", "course", "course_preference", "programme"],
    "institution":      ["institution", "college", "university", "school"],
    "date_of_birth":    ["date_of_birth", "dob", "birth_date"],
    "passport_number":  ["passport_number", "passport_no"],
    "address":          ["address", "home_address", "destination_address", "service_address"],
    "nationality":      ["nationality", "country_of_nationality"],
    "bank_name":        ["bank_name", "bank"],
    "account_number":   ["account_number", "iban"],
    "employer_name":    ["employer_name", "employer", "company_name"],
}

_NAME_FIELDS = {
    "full_name", "employee_name", "student_name",
    "account_holder", "name", "person1_name",
}


def _parse_any_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        from dateutil import parser as _du_parser  # type: ignore

        return _du_parser.parse(text, dayfirst=True, fuzzy=True).date()
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
        "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y",
        "%m/%Y", "%B %Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _resolve_form_value(field: str, form_data: Dict[str, Any]) -> Optional[str]:
    for key in _FIELD_TO_FORM_MAP.get(field, []):
        val = form_data.get(key)
        if val:
            return str(val).strip()
    return None


def cross_check_document_vs_form(
    extracted_fields: Dict[str, Any],
    form_data: Dict[str, Any],
    document_type: str,
) -> Dict[str, Any]:
    inconsistencies: List[str] = []
    verified_fields: Dict[str, Any] = {}
    name_match: Optional[bool] = None  # True wins; only flips False if NO field matches
    name_on_document: Optional[str] = None
    expiry_valid: Optional[bool] = None
    expiry_date_found: Optional[str] = None

    # First pass: collect every name-like value the QA model produced
    candidate_names: List[str] = [
        str(v) for k, v in extracted_fields.items()
        if k in _NAME_FIELDS and v
    ]
    form_name = _resolve_form_value("full_name", form_data)
    if form_name and candidate_names:
        best_candidate, score, matched = best_name_match(form_name, candidate_names)
        name_on_document = best_candidate
        if matched:
            name_match = True
            verified_fields["name"] = best_candidate
        else:
            name_match = False
            inconsistencies.append(
                f"Name on document ('{best_candidate}') does not match "
                f"the application name ('{form_name}')."
            )

    for doc_field, doc_value in extracted_fields.items():
        if not doc_value or doc_field in _NAME_FIELDS:
            continue

        if doc_field == "expiry_date":
            expiry_date_found = str(doc_value)
            parsed = _parse_any_date(doc_value)
            if parsed:
                expired = parsed < date.today()
                expiry_valid = not expired
                if expired:
                    inconsistencies.append(
                        f"Document expired on {parsed.isoformat()}."
                    )

        elif doc_field == "date_of_birth":
            form_val = _resolve_form_value(doc_field, form_data)
            if form_val:
                doc_dob = _parse_any_date(doc_value)
                form_dob = _parse_any_date(form_val)
                if doc_dob and form_dob:
                    if doc_dob == form_dob:
                        verified_fields["date_of_birth"] = doc_dob.isoformat()
                    else:
                        inconsistencies.append(
                            f"Date of birth on document ('{doc_dob.isoformat()}') does not match "
                            f"the application date of birth ('{form_dob.isoformat()}')."
                        )

        else:
            form_val = _resolve_form_value(doc_field, form_data)
            if form_val:
                # Use the same fuzzy comparator we use for names — handles
                # OCR noise consistently across all field types. We ONLY
                # record positive verifications here. Negative outcomes are
                # left silent because the QA model is too noisy to be
                # treated as authoritative for arbitrary fields (it would
                # produce false-positive "Issue Found" alerts even when the
                # form data is correct). Authoritative checks (name, DOB,
                # expiry, document type) are handled elsewhere.
                _, _score, matched = best_name_match(
                    form_val, [str(doc_value)], min_token_ratio=0.78
                )
                if matched:
                    verified_fields[doc_field] = doc_value

    # If we never even attempted a name comparison (nothing extracted),
    # that's an unverifiable document — the validation service decides
    # whether to flag it (it has the OCR-text fallback path we don't).
    _ = document_type  # accepted for future per-type rules; intentionally unused

    # Build a plain-English summary (no external call needed)
    summary_parts: List[str] = []
    if name_match is True:
        summary_parts.append("name matches")
    elif name_match is False:
        summary_parts.append("name does NOT match")
    if expiry_valid is True:
        summary_parts.append("document is valid")
    elif expiry_valid is False:
        summary_parts.append("document is EXPIRED")
    if inconsistencies:
        summary_parts.append(f"{len(inconsistencies)} inconsistency(ies) found")
    ai_summary = ("Document check: " + ", ".join(summary_parts) + ".") if summary_parts else ""

    overall_valid = (name_match is not False) and (expiry_valid is not False) and not inconsistencies

    return {
        "ai_name_match":       name_match,
        "ai_name_on_document": name_on_document,
        "ai_expiry_valid":     expiry_valid,
        "ai_expiry_date_found": expiry_date_found,
        "ai_verified_fields":  verified_fields,
        "ai_inconsistencies":  inconsistencies,
        "ai_summary":          ai_summary,
        "ai_overall_valid":    overall_valid,
    }
