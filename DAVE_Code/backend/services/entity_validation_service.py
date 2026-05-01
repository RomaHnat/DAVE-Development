from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from backend.database import db
from backend.services.ner_service import (
    extract_date_of_birth,
)
_EXPECTED_ENTITIES: Dict[str, List[str]] = {
    "passport": ["names", "id_numbers", "dates"],
    "id_card": ["names", "id_numbers", "dates"],
    "bank_statement": ["names", "dates"],
    "utility_bill": ["names", "addresses", "dates"],
    "certificate": ["names", "dates"],
    "travel_insurance": ["dates"],
    "photo": [],
    "default": ["names"],
}

# Confidence below this triggers a warning (not an error)
_LOW_CONFIDENCE_THRESHOLD = 0.70

def validate_extracted_entities(
    entities: Dict[str, List[Dict[str, Any]]],
    doc_type: Optional[str] = None,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "is_valid": True,
        "issues": [],
        "warnings": [],
    }

    expected = _EXPECTED_ENTITIES.get(doc_type or "default",
                                      _EXPECTED_ENTITIES["default"])

    for entity_type in expected:
        entity_list = entities.get(entity_type, [])
        if not entity_list:
            result["issues"].append(
                f"Expected entity not found: '{entity_type}'."
            )
            result["is_valid"] = False

    for entity_type, entity_list in entities.items():
        for entry in entity_list:
            conf = entry.get("confidence", 1.0)
            if conf < _LOW_CONFIDENCE_THRESHOLD:
                result["warnings"].append(
                    f"Low confidence for {entity_type} "
                    f"'{entry.get('value', '?')}' ({conf:.0%})."
                )

    return result

def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def check_data_consistency(application_id: str) -> Dict[str, Any]:

    report: Dict[str, Any] = {
        "is_consistent": True,
        "issues": [],
        "cross_document_checks": [],
    }

    from bson import ObjectId

    try:
        oid = ObjectId(application_id)
    except Exception:
        report["issues"].append({"type": "invalid_application_id"})
        report["is_consistent"] = False
        return report

    documents = await db.documents.find({"application_id": oid}).to_list(None)

    if len(documents) < 2:
        report["cross_document_checks"].append(
            "Fewer than two documents available – skipping cross-document checks."
        )
        return report

    #Collect names 
    all_names: List[tuple] = []
    for doc in documents:
        entities = doc.get("extracted_entities") or {}
        for name_entry in entities.get("names", []):
            all_names.append((name_entry["value"], doc.get("document_type", "unknown")))

    if len(all_names) >= 2:
        name_values = [n for n, _ in all_names]
        for i in range(len(name_values)):
            for j in range(i + 1, len(name_values)):
                sim = _name_similarity(name_values[i], name_values[j])
                if sim < 0.70:
                    report["issues"].append({
                        "type": "name_mismatch",
                        "name_a": name_values[i],
                        "name_b": name_values[j],
                        "similarity": round(sim, 3),
                    })
                    report["is_consistent"] = False
        report["cross_document_checks"].append(
            f"Compared {len(name_values)} name(s) across documents."
        )

    #Collect ID numbers
    all_ids: List[str] = []
    for doc in documents:
        entities = doc.get("extracted_entities") or {}
        for id_entry in entities.get("id_numbers", []):
            all_ids.append(id_entry["value"])

    if len(set(all_ids)) > 1:
        report["issues"].append({
            "type": "id_mismatch",
            "ids_found": list(set(all_ids)),
        })
        report["is_consistent"] = False
        report["cross_document_checks"].append("ID numbers differ across documents.")
    elif all_ids:
        report["cross_document_checks"].append("ID numbers are consistent.")

    #Collect dates of birth
    dobs: List[str] = []
    for doc in documents:
        text = doc.get("extracted_text") or ""
        entities = doc.get("extracted_entities") or {}
        dob = extract_date_of_birth(text, entities)
        if dob:
            dobs.append(dob)

    if len(set(dobs)) > 1:
        report["issues"].append({
            "type": "dob_mismatch",
            "dobs_found": list(set(dobs)),
        })
        report["is_consistent"] = False
        report["cross_document_checks"].append("Dates of birth differ across documents.")
    elif dobs:
        report["cross_document_checks"].append("Dates of birth are consistent.")

    return report

async def compare_form_data_with_documents(
    application_id: str,
    form_data: Dict[str, Any],
) -> Dict[str, Any]:

    report: Dict[str, Any] = {
        "is_consistent": True,
        "mismatches": [],
    }

    from bson import ObjectId

    try:
        oid = ObjectId(application_id)
    except Exception:
        return report

    documents = await db.documents.find({"application_id": oid}).to_list(None)
    if not documents:
        return report

    form_name = (form_data.get("full_name") or "").lower().strip()
    form_email = (form_data.get("email") or "").lower().strip()

    for doc in documents:
        entities = doc.get("extracted_entities") or {}
        doc_type = doc.get("document_type", "unknown")

        #Name check
        doc_names = [e["value"].lower() for e in entities.get("names", [])]
        if form_name and doc_names:
            found = any(
                _name_similarity(form_name, dn) >= 0.75 for dn in doc_names
            )
            if not found:
                report["mismatches"].append({
                    "field": "name",
                    "form_value": form_name,
                    "document_value": doc_names[0],
                    "document_type": doc_type,
                    "severity": "error",
                })
                report["is_consistent"] = False

        #Email check (advisory – email may not appear on ID)
        doc_emails = [e["value"].lower() for e in entities.get("emails", [])]
        if form_email and doc_emails and form_email not in doc_emails:
            report["mismatches"].append({
                "field": "email",
                "form_value": form_email,
                "document_value": doc_emails[0],
                "document_type": doc_type,
                "severity": "warning",
            })

    return report

async def run_full_document_validation(
    application_id: str,
    form_data: Dict[str, Any],
) -> Dict[str, Any]:
    
    consistency = await check_data_consistency(application_id)
    form_vs_docs = await compare_form_data_with_documents(application_id, form_data)

    all_issues = consistency["issues"] + [
        m for m in form_vs_docs["mismatches"] if m.get("severity") == "error"
    ]
    all_warnings = [
        m for m in form_vs_docs["mismatches"] if m.get("severity") == "warning"
    ]

    return {
        "is_valid": len(all_issues) == 0,
        "is_consistent": consistency["is_consistent"] and form_vs_docs["is_consistent"],
        "issues": all_issues,
        "warnings": all_warnings,
        "cross_document_checks": consistency.get("cross_document_checks", []),
    }
