from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


_DocumentProfile = Dict[str, Any]

DOCUMENT_PROFILES: Dict[str, _DocumentProfile] = {
    "passport": {
        "label": "Passport",
        "synonyms": [
            "passport", "passport or id", "passport or travel document",
            "travel document", "national passport",
        ],
        "patterns": [
            (r"P<[A-Z]{3}", 12),
            (r"\bMRZ\b", 6),
            (r"\bpassport\s*(no\.?|number|num\b|n[°o]\b)", 8),
            (r"\bsurname\b[\s\S]{0,40}\bgiven\s*names?\b", 6),
            (r"\bnationality\b[\s\S]{0,80}\bdate\s*of\s*birth\b", 5),
            (r"\bissuing\s*authority\b", 4),
            (r"\bplace\s*of\s*(issue|birth)\b", 3),
            (r"\bdate\s*of\s*expir(y|ation)\b", 2),
            (r"\bsex\s*[:/]?\s*[MF]\b", 2),
            (r"\bpassport\b", 2),
        ],
        "negative_patterns": [
            (r"\bP60\b", 8),
            (r"\bbank\s*statement\b", 6),
            (r"\butility\s*bill\b", 6),
        ],
    },
    "p60": {
        "label": "P60 (End of Year Tax Certificate)",
        "synonyms": [
            "p60", "proof of income", "end of year certificate",
            "end of year tax certificate", "p60 end of year",
            "p60 end of year tax certificate",
        ],
        "patterns": [
            (r"\bP60\b", 12),
            (r"end\s*of\s*year\s*(tax\s*)?certificate", 10),
            (r"\bemployee'?s?\s*PPS\s*(no|number)\b", 5),
            (r"\bemployer\s*(reg(istered)?\s*)?(no|number)\b", 4),
            (r"\btotal\s*pay\b", 4),
            (r"\btax\s*deducted\b", 4),
            (r"\bUSC\b", 3),
            (r"\bPRSI\b", 4),
            (r"\btax\s*year\b", 3),
            (r"\bgross\s*pay\b", 2),
            (r"\bemployer\b[\s\S]{0,80}\bemployee\b", 2),
            (r"\brevenue\s*commissioners\b", 4),
        ],
        "negative_patterns": [
            (r"P<[A-Z]{3}", 8),
            (r"\bbank\s*statement\b", 5),
        ],
        # Patterns that must be present for the document to be a valid proof
        # of income.  A P60 must show a tax year and earnings/tax figures.
        # A Revenue Notice of Assessment is also acceptable.
        "required_indicators": [
            (
                r"\btax\s*year\b|\b(20\d{2})[\s/\-](20\d{2}|\d{2})\b",
                "No tax year found. A valid P60 or tax assessment must state the tax year it covers.",
            ),
            (
                r"\b(total|gross)\s*pay\b|\btaxable\s*income\b|\btotal\s*income\b",
                "No pay or income figure found. The document must show total/gross pay or taxable income.",
            ),
            (
                r"\btax\s*deducted\b|\bincome\s*tax\b|\bnotice\s*of\s*assessment\b|\bPAYE\b",
                "No tax deducted or assessment figure found. Expected PAYE / tax deducted or a Revenue Notice of Assessment.",
            ),
        ],
    },
    "payslip": {
        "label": "Payslip",
        "synonyms": ["payslip", "pay slip", "salary slip", "wage slip"],
        "patterns": [
            (r"\bpay[\s-]?slip\b", 10),
            (r"\bpay\s*period\b", 6),
            (r"\bpay\s*date\b", 5),
            (r"\bnet\s*pay\b", 5),
            (r"\bgross\s*pay\b", 4),
            (r"\bytd\b", 2),
            (r"\bdeductions?\b", 2),
        ],
        "negative_patterns": [
            (r"\bP60\b", 8),
            (r"end\s*of\s*year\s*(tax\s*)?certificate", 10),
        ],
    },
    "bank_statement": {
        "label": "Bank Statement",
        "synonyms": ["bank statement", "account statement", "statement of account"],
        "patterns": [
            (r"\bbank\s*statement\b", 12),
            (r"\bstatement\s*of\s*account\b", 10),
            (r"\bopening\s*balance\b", 6),
            (r"\bclosing\s*balance\b", 6),
            (r"\bIBAN\b", 4),
            (r"\bBIC\b", 3),
            (r"\bsort\s*code\b", 4),
            (r"\baccount\s*(no|number)\b", 3),
            (r"\bavailable\s*balance\b", 3),
            (r"\btransaction\s*(s|history|list)\b", 2),
            (r"\bwithdrawals?\b[\s\S]{0,40}\bdeposits?\b", 3),
        ],
        # A visa-support bank statement must cover the last 3 months and
        # show the account holder name, IBAN/account number, and a balance.
        "required_indicators": [
            (
                r"\bIBAN\b|\baccount\s*(no|number|num)\b|\bsort\s*code\b",
                "No account number or IBAN found. The statement must identify the account holder's account.",
            ),
            (
                r"\b(opening|closing|available|current)\s*balance\b",
                "No balance information found. The statement must show the account balance.",
            ),
            (
                r"\bstatement\s*(period|date|from|for)\b|\bfrom\s+\d|\bperiod\s*:\s*\d",
                "No statement period or date found. The statement must show the period it covers (last 3 months required for visa applications).",
            ),
        ],
    },
    "utility_bill": {
        "label": "Utility Bill",
        "synonyms": ["utility bill", "proof of address", "electricity bill", "gas bill"],
        "patterns": [
            (r"\butility\s*bill\b", 10),
            (r"\belectricity\s*(bill|usage|account)\b", 8),
            (r"\bgas\s*(bill|usage|account)\b", 7),
            (r"\bwater\s*(bill|usage|account)\b", 6),
            (r"\bmeter\s*read(ing)?\b", 6),
            (r"\bkWh\b", 4),
            (r"\bMPRN\b", 5),
            (r"\bGPRN\b", 5),
            (r"\bbill(ing)?\s*period\b", 3),
            (r"\bamount\s*due\b", 3),
            (r"\baccount\s*(no|number)\b", 2),
        ],
    },
    "enrollment_letter": {
        "label": "Student Enrolment Letter",
        "synonyms": [
            "enrollment letter", "enrolment letter",
            "student enrollment letter", "student enrolment letter",
            "enrollment certificate", "enrolment certificate",
            "letter of enrollment", "letter of enrolment",
            "proof of enrolment", "proof of enrollment",
        ],
        "patterns": [
            (r"\benrol(l)?ment\s*(letter|certificate|confirmation)\b", 10),
            (r"\bletter\s*of\s*enrol(l)?ment\b", 10),
            (r"\bconfirmation\s*of\s*enrol(l)?ment\b", 9),
            (r"\bregistered\s*as\s*a\s*(full|part)[\s-]?time\s*student\b", 8),
            (r"\bacademic\s*year\b", 4),
            (r"\b(student|programme|course)\s*(name|title|of\s*study)\b", 3),
            (r"\b(college|university|institute)\s*of\b", 2),
            (r"\benrolled\s*in\b", 3),
            (r"\bstudent\s*(id|number)\b", 2),
        ],
        # Must confirm the student is enrolled AND reference the current
        # academic year.  SUSI requires a letter for the current year.
        "required_indicators": [
            (
                r"\benrol(l)?ed\b|\bregistered\s*(as|for)\b|\bcurrently\s*enrolled\b",
                "No enrolment confirmation found. The letter must confirm the student is currently enrolled.",
            ),
            (
                # Matches e.g. 2024/25, 2025/26, 2025/2026, 2026/27, 2026/2027
                r"\b20(2[4-9]|[3-9]\d)[/\-](20(2[5-9]|[3-9]\d)|[2-9]\d)\b",
                "No current academic year found (e.g. 2025/26). The letter must reference the academic year for which enrolment is confirmed.",
            ),
            (
                r"\b(course|programme|module|degree|qualification)\b",
                "No course or programme name found. The letter must state the course or programme the student is enrolled in.",
            ),
        ],
    },
    "birth_certificate": {
        "label": "Birth Certificate",
        "synonyms": ["birth certificate", "certificate of birth"],
        "patterns": [
            (r"\bbirth\s*certificate\b", 12),
            (r"\bcertificate\s*of\s*birth\b", 12),
            (r"\bplace\s*of\s*birth\b", 4),
            (r"\bdate\s*of\s*birth\b", 2),
            (r"\bfather'?s?\s*name\b", 4),
            (r"\bmother'?s?\s*name\b", 4),
            (r"\bregistrar\b", 4),
            (r"\bregistration\s*district\b", 3),
        ],
    },
    "marriage_certificate": {
        "label": "Marriage Certificate",
        "synonyms": ["marriage certificate", "certificate of marriage"],
        "patterns": [
            (r"\bmarriage\s*certificate\b", 12),
            (r"\bcertificate\s*of\s*marriage\b", 12),
            (r"\bdate\s*of\s*marriage\b", 6),
            (r"\bplace\s*of\s*marriage\b", 5),
            (r"\bsolemniz(ed|ation)\b", 4),
            (r"\bbride\b[\s\S]{0,40}\bgroom\b", 4),
            (r"\bregistrar\b", 3),
        ],
    },
    "driving_licence": {
        "label": "Driving Licence",
        "synonyms": ["driving licence", "driving license", "driver licence", "driver license"],
        "patterns": [
            (r"\bdriving\s*licen[cs]e\b", 10),
            (r"\bdriver(?:'s)?\s*licen[cs]e\b", 10),
            (r"\bcategor(y|ies)\s*[A-Z]\b", 3),
            (r"\bvehicle\s*categories\b", 3),
            (r"\blicen[cs]e\s*(no|number)\b", 4),
            (r"\bplace\s*of\s*birth\b", 1),
        ],
    },
    "travel_insurance": {
        "label": "Travel Insurance",
        "synonyms": ["travel insurance", "travel insurance policy", "insurance certificate"],
        "patterns": [
            (r"\btravel\s*insurance\b", 12),
            (r"\binsurance\s*(certificate|policy)\b", 6),
            (r"\bpolicy\s*(no|number)\b", 4),
            (r"\bperiod\s*of\s*cover\b", 4),
            (r"\binsured\s*person\b", 3),
            (r"\bmedical\s*expenses\b", 3),
            (r"\b(emergency|repatriation)\b", 2),
        ],
        # A visa travel insurance policy must show a policy number, the
        # coverage period (departure → return), and emergency/medical cover.
        "required_indicators": [
            (
                r"\bpolicy\s*(no\.?|number|num\b|#)\b",
                "No policy number found. A valid travel insurance certificate must include a policy number.",
            ),
            (
                r"\b(period\s*of\s*(cover|insurance)|coverage\s*period|travel\s*(dates?|period)|valid\s*from|departure\s*date|journey\s*dates?|from\s*\d{1,2}[\s/\-])\b",
                "No coverage dates found. The policy must state the dates it covers to confirm the full duration of stay is insured.",
            ),
            (
                r"\b(medical\s*expenses|emergency\s*(medical|treatment|assistance)|hospitalisation|medical\s*evacuation)\b",
                "No medical/emergency coverage found. The policy must include medical expenses or emergency assistance cover as required for visa applications.",
            ),
        ],
    },
    "id_card": {
        "label": "National ID Card",
        "synonyms": [
            "id card", "national id card", "national id", "identity card",
            "national identity card",
        ],
        "patterns": [
            (r"\bidentity\s*card\b", 10),
            (r"\bnational\s*id(entity)?\b", 8),
            (r"\bid\s*card\b", 6),
            (r"\bcardholder\b", 3),
            (r"\bdate\s*of\s*birth\b", 2),
            (r"\bissuing\s*authority\b", 2),
        ],
        "negative_patterns": [
            (r"\bP60\b", 6),
            (r"\bbank\s*statement\b", 6),
            (r"\bpassport\s*(no|number)\b", 4),
        ],
    },
    "passport_photo": {
        "label": "Passport Photo",
        "synonyms": ["passport photo", "passport photograph", "id photo"],
        "patterns": [],
    },
    "personal_statement": {
        "label": "Personal Statement",
        "synonyms": ["personal statement", "statement of purpose"],
        "patterns": [
            (r"\bpersonal\s*statement\b", 10),
            (r"\bstatement\s*of\s*purpose\b", 9),
        ],
    },
    "reference_letter": {
        "label": "Reference Letter",
        "synonyms": ["reference letter", "letter of reference", "recommendation letter", "letter of recommendation"],
        "patterns": [
            (r"\bletter\s*of\s*(reference|recommendation)\b", 10),
            (r"\b(reference|recommendation)\s*letter\b", 8),
            (r"\bto\s*whom\s*it\s*may\s*concern\b", 4),
            (r"\bI\s*(strongly\s*)?recommend\b", 4),
        ],
    },
    "educational_certificate": {
        "label": "Educational Certificate / Transcript",
        "synonyms": [
            "educational certificate", "educational certificates",
            "transcript", "academic transcript",
            "diploma", "degree certificate", "leaving certificate",
        ],
        "patterns": [
            (r"\btranscript\s*of\s*(records|grades)\b", 8),
            (r"\bacademic\s*transcript\b", 8),
            (r"\bdegree\s*(certificate|awarded|conferred)\b", 7),
            (r"\bdiploma\b", 5),
            (r"\bleaving\s*certificate\b", 8),
            (r"\bbachelor\s*of\b", 4),
            (r"\bmaster\s*of\b", 4),
            (r"\bclass\s*honou?rs\b", 3),
            (r"\bgrade\s*point\s*average\b", 3),
            (r"\bGPA\b", 2),
        ],
    },
}

# Document types that are interchangeable for a given upload label.
# If the requested canonical and detected type are in the same group,
# the document is considered verified even though the keys differ.
_EQUIVALENT_GROUPS: List[frozenset] = [
    frozenset({"passport", "id_card"}),  # "Passport or ID" accepts either
]

# Synonym → canonical key (built once at import time)
_SYNONYM_INDEX: Dict[str, str] = {}
for _key, _profile in DOCUMENT_PROFILES.items():
    for _syn in _profile.get("synonyms", []):
        _SYNONYM_INDEX[_syn.lower().strip()] = _key
    _SYNONYM_INDEX[_key.replace("_", " ")] = _key
    _SYNONYM_INDEX[_profile["label"].lower()] = _key


def check_required_indicators(
    extracted_text: str,
    canonical: str,
) -> List[str]:

    profile = DOCUMENT_PROFILES.get(canonical)
    if not profile:
        return []
    indicators: List[Tuple[str, str]] = profile.get("required_indicators", [])
    if not indicators:
        return []

    issues: List[str] = []
    for pattern, missing_message in indicators:
        if not re.search(pattern, extracted_text, flags=re.IGNORECASE):
            issues.append(missing_message)
            logger.info(
                "[Classifier] required_indicator MISSING — canonical=%r  pattern=%r",
                canonical, pattern,
            )
        else:
            logger.info(
                "[Classifier] required_indicator OK — canonical=%r  pattern=%r",
                canonical, pattern,
            )
    return issues


def canonical_type(requested_type: str) -> Optional[str]:

    if not requested_type:
        return None
    key = requested_type.lower().strip()
    # Direct synonym hit
    if key in _SYNONYM_INDEX:
        return _SYNONYM_INDEX[key]
    # Substring fallback — pick the longest synonym that fits the input
    best: Tuple[int, Optional[str]] = (0, None)
    for syn, canonical in _SYNONYM_INDEX.items():
        if syn in key or key in syn:
            if len(syn) > best[0]:
                best = (len(syn), canonical)
    return best[1]


def _score_profile(text: str, profile: _DocumentProfile) -> int:
    score = 0
    for pattern, weight in profile.get("patterns", []):
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += weight
    for pattern, weight in profile.get("negative_patterns", []):
        if re.search(pattern, text, flags=re.IGNORECASE):
            score -= weight
    return score


def classify_document(text: str) -> Dict[str, Any]:

    if not text or not text.strip():
        return {
            "detected_type": None,
            "detected_label": None,
            "confidence": 0.0,
            "scores": {},
        }

    scores: List[Tuple[str, int]] = []
    for key, profile in DOCUMENT_PROFILES.items():
        if not profile.get("patterns"):
            continue
        score = _score_profile(text, profile)
        scores.append((key, score))

    scores.sort(key=lambda kv: kv[1], reverse=True)
    if not scores or scores[0][1] <= 0:
        return {
            "detected_type": None,
            "detected_label": None,
            "confidence": 0.0,
            "scores": {k: s for k, s in scores},
        }

    top_key, top_score = scores[0]
    runner_score = scores[1][1] if len(scores) > 1 else 0
    # Confidence: how dominant the top score is, normalised against a
    # "very confident" baseline of 30 raw points.
    margin = max(top_score - max(runner_score, 0), 1)
    confidence = min(1.0, (top_score / 30.0) * 0.6 + (margin / 30.0) * 0.4)

    return {
        "detected_type": top_key,
        "detected_label": DOCUMENT_PROFILES[top_key]["label"],
        "confidence": round(float(confidence), 3),
        "scores": {k: s for k, s in scores},
    }


def verify_against_requested(
    extracted_text: str,
    requested_type: str,
    min_confidence: float = 0.30,
) -> Dict[str, Any]:

    classification = classify_document(extracted_text)
    detected = classification["detected_type"]
    confidence = classification["confidence"]
    canonical = canonical_type(requested_type)

    result = {
        "detected_type": detected,
        "detected_label": classification["detected_label"],
        "confidence": confidence,
        "requested_canonical": canonical,
        "scores": classification["scores"],
    }

    # Profile not in our catalogue (e.g. "Personal Statement" with no
    # patterns) — we cannot say either way, so don't fail validation.
    if canonical is None:
        result["type_verified"] = None
        result["reason"] = "Requested document type is not recognised by the offline classifier."
        return result

    if detected is None or confidence < min_confidence:
        result["type_verified"] = None
        result["reason"] = "Not enough textual evidence to confirm the document type."
        return result

    if detected == canonical:
        result["type_verified"] = True
        result["reason"] = f"Document content is consistent with a {result['detected_label']}."
        return result

    # Allow equivalent types — e.g. a real passport uploaded as "Passport or ID"
    # should not fail because the classifier correctly identifies it as "passport"
    # while the canonical for "Passport or ID" is "id_card" (or vice-versa).
    for group in _EQUIVALENT_GROUPS:
        if detected in group and canonical in group:
            result["type_verified"] = True
            result["reason"] = f"Document content is consistent with a {result['detected_label']}."
            return result

    result["type_verified"] = False
    result["reason"] = (
        f"Document was uploaded as '{requested_type}' but the content "
        f"looks like a {result['detected_label']}."
    )
    return result
