from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cyrillic Unicode ranges:
#   U+0400–U+04FF  — Cyrillic
#   U+0500–U+052F  — Cyrillic Supplement
#   U+2DE0–U+2DFF  — Cyrillic Extended-A
#   U+A640–U+A69F  — Cyrillic Extended-B
# Stripping these from OCR text before NER prevents bilingual field labels
# (e.g. Ukrainian "Номер паспорта / Passport") from being misclassified as
# person names.  The original text is kept intact for MRZ parsing and the
# full-text token scan, which are both immune to Cyrillic noise.
_CYRILLIC_RE = re.compile(r'[\u0400-\u04FF\u0500-\u052F\u2DE0-\u2DFF\uA640-\uA69F]+')


def _strip_cyrillic(text: str) -> str:

    cleaned = _CYRILLIC_RE.sub(' ', text)
    # Collapse runs of whitespace left behind after removal
    return re.sub(r'  +', ' ', cleaned)

_TRANSFORMERS_AVAILABLE = False
_SPACY_AVAILABLE = False
_ner_pipeline = None
_nlp = None
_ner_pipeline_initialized = False
_nlp_initialized = False


def _ensure_ner_pipeline() -> None:

    global _ner_pipeline, _TRANSFORMERS_AVAILABLE, _ner_pipeline_initialized
    if _ner_pipeline_initialized:
        return
    _ner_pipeline_initialized = True
    try:
        import transformers as _tf  # type: ignore
        # Silence UNEXPECTED-key warnings and the weight-loading progress bar.
        # The bert.pooler.dense.* keys belong to the masked-LM pre-training
        # head and are intentionally unused by the token-classification head.
        _tf.logging.set_verbosity_error()
        _tf.utils.logging.disable_progress_bar()
        from transformers import pipeline as _hf_pipeline
        logger.info("[NER] Loading transformers NER pipeline (first use)\u2026")
        _ner_pipeline = _hf_pipeline(
            "ner",
            model="dbmdz/bert-large-cased-finetuned-conll03-english",
            aggregation_strategy="simple",
        )
        _TRANSFORMERS_AVAILABLE = True
        logger.info("[NER] Transformers NER pipeline ready.")
    except Exception as exc:
        logger.warning("[NER] Transformers not available: %s", exc)


def _ensure_spacy() -> None:

    global _nlp, _SPACY_AVAILABLE, _nlp_initialized
    if _nlp_initialized:
        return
    _nlp_initialized = True
    try:
        import spacy as _spacy_module  # type: ignore
        _nlp = _spacy_module.load("en_core_web_sm")
        _SPACY_AVAILABLE = True
        logger.info("[NER] spaCy en_core_web_sm loaded.")
    except Exception as exc:
        logger.info("[NER] spaCy en_core_web_sm not available (transformers NER will be used instead): %s", exc)

def extract_entities_with_transformers(text: str) -> List[Dict[str, Any]]:
    _ensure_ner_pipeline()
    if not _TRANSFORMERS_AVAILABLE or _ner_pipeline is None:
        return []

    results = _ner_pipeline(text)
    return [
        {
            "entity_type": ent["entity_group"],
            "text": ent["word"],
            "confidence": round(float(ent["score"]), 4),
            "start": ent["start"],
            "end": ent["end"],
            "source": "transformers",
        }
        for ent in results
    ]

def extract_entities_with_spacy(text: str) -> List[Dict[str, Any]]:
    _ensure_spacy()
    if not _SPACY_AVAILABLE or _nlp is None:
        return []

    doc = _nlp(text)
    return [
        {
            "entity_type": ent.label_,
            "text": ent.text,
            "start": ent.start_char,
            "end": ent.end_char,
            "source": "spacy",
        }
        for ent in doc.ents
    ]


def combine_entity_results(
    transformer_entities: List[Dict[str, Any]],
    spacy_entities: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    all_entities = transformer_entities + spacy_entities
    seen: set = set()
    unique: List[Dict[str, Any]] = []

    for entity in all_entities:
        key = (entity["text"].lower(), entity["entity_type"])
        if key not in seen:
            seen.add(key)
            unique.append(entity)

    return sorted(unique, key=lambda x: x.get("start", 0))

# Passport MRZ line 1: starts with P, exactly 44 chars, letters and '<' ONLY (no digits).
# Digits are only allowed on line 2 (passport number, DOB, expiry).
# This eliminates non-MRZ lines that happen to be 44 uppercase chars long.
_MRZ_LINE1_RE = re.compile(r'^P[A-Z<]{43}$')
# Line 2 may contain digits
_MRZ_LINE2_RE = re.compile(r'^[A-Z0-9<]{44}$')


def _parse_mrz_lines(text: str) -> Optional[tuple]:

    lines = [ln.strip() for ln in text.splitlines()]
    for i in range(len(lines) - 1):
        l1, l2 = lines[i], lines[i + 1]
        # Accept '<<' (standard filler) OR 'KK' when OCR misreads '<' as 'K'.
        # The KK path only fires when the line has NO real '<' chars at all,
        # preventing false positives on lines that naturally contain "KK".
        has_sep = ('<<' in l1[5:]) or ('<' not in l1 and 'KK' in l1[5:])
        if (
            _MRZ_LINE1_RE.match(l1)
            and _MRZ_LINE2_RE.match(l2)
            and has_sep
        ):
            return (l1, l2)
    # Fallback: scan stripped text for the MRZ pair concatenated without whitespace
    stripped = re.sub(r'\s+', '', text)
    m = re.search(r'(P[A-Z<]{43})([A-Z0-9<]{44})', stripped)
    if m:
        l1, l2 = m.group(1), m.group(2)
        has_sep = ('<<' in l1[5:]) or ('<' not in l1 and 'KK' in l1[5:])
        if has_sep:
            return (l1, l2)
    return None


def _mrz_field_to_text(field: str) -> str:

    return field.replace('<', ' ').strip()


def _mrz_year_to_full(yy: int, cutoff: int = 30) -> int:

    return 2000 + yy if yy <= cutoff else 1900 + yy


def _extract_mrz_name_field(name_field: str, country_code: str = "") -> Optional[str]:
    #Pass 1: standard '<' filler
    if '<<' in name_field:
        idx = name_field.index('<<')
        surname_raw = name_field[:idx].rstrip('<')
        given_raw   = name_field[idx + 2:]
        given_parts = [
            p.replace('<', '').strip()
            for p in given_raw.split('<<')
            if p.replace('<', '').strip()
        ]
        if re.match(r'^[A-Z]{2,}$', surname_raw) and given_parts:
            given = ' '.join(p.capitalize() for p in given_parts)
            full_name = f"{given} {surname_raw.capitalize()}"
            if country_code and country_code.upper() in full_name.upper().split():
                logger.warning(
                    "MRZ name contains country code %r — likely garbled: %r",
                    country_code, full_name,
                )
                return None
            return full_name

    #Pass 2: K-as-filler fallback (OCR reads '<' as 'K')
    # Only attempt when the name field has NO real '<' chars at all
    if '<' not in name_field and 'KK' in name_field:
        for m in re.finditer(r'KK+', name_field):
            idx = m.start()
            surname_raw = re.sub(r'K+$', '', name_field[:idx])  # strip trailing K-fillers
            if not re.match(r'^[A-Z]{2,}$', surname_raw):
                continue
            remaining = name_field[m.end():]
            given_parts = [
                p for p in re.split(r'K{2,}', remaining)
                if re.match(r'^[A-Z]{2,}$', p)
            ]
            if given_parts:
                given = ' '.join(p.capitalize() for p in given_parts)
                full_name = f"{given} {surname_raw.capitalize()}"
                if country_code and country_code.upper() in full_name.upper().split():
                    logger.warning(
                        "MRZ name (K-fallback) contains country code %r — garbled: %r",
                        country_code, full_name,
                    )
                    continue
                return full_name

    return None


def parse_mrz(text: str) -> Optional[Dict[str, Any]]:

    pair = _parse_mrz_lines(text)
    if not pair:
        return None

    line1, line2 = pair
    result: Dict[str, Any] = {"raw_line1": line1, "raw_line2": line2}

    # Country code at positions 2-4 (used for name sanity check)
    country_code = line1[2:5] if len(line1) >= 5 else ""

    #Name (line 1, positions 5-43)
    name_field = line1[5:44]
    result["full_name"] = _extract_mrz_name_field(name_field, country_code)

    #Date of birth (line 2, positions 13-18, format YYMMDD)
    try:
        dob_raw = line2[13:19]
        yy, mm, dd = int(dob_raw[:2]), int(dob_raw[2:4]), int(dob_raw[4:6])
        yyyy = _mrz_year_to_full(yy)
        result["date_of_birth"] = f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    except Exception:
        result["date_of_birth"] = None

    #Expiry date (line 2, positions 21–26, format YYMMDD)
    try:
        exp_raw = line2[21:27]
        yy, mm, dd = int(exp_raw[:2]), int(exp_raw[2:4]), int(exp_raw[4:6])
        yyyy = _mrz_year_to_full(yy, cutoff=70)  # passports expire in near future
        result["expiry_date"] = f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    except Exception:
        result["expiry_date"] = None

    logger.info(
        "MRZ parsed — name: %r  dob: %s  expiry: %s",
        result.get("full_name"),
        result.get("date_of_birth"),
        result.get("expiry_date"),
    )
    return result


# Irish PPS number: 7 digits followed by 1-2 uppercase letters
_PATTERN_PPS = re.compile(r"\b\d{7}[A-Z]{1,2}\b")
# Passport number: 2 uppercase letters followed by 7 digits
_PATTERN_PASSPORT = re.compile(r"\b[A-Z]{2}\d{7}\b")
# Generic student / staff ID (T00xxxxxx)
_PATTERN_STUDENT_ID = re.compile(r"\bT\d{8}\b")
# Email
_PATTERN_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)
# Irish/UK phone (landline or mobile)
_PATTERN_PHONE = re.compile(
    r"\b(?:\+353|0)[\s\-]?\d{1,2}[\s\-]?\d{3}[\s\-]?\d{4}\b"
)
# Dates in various formats
_DATE_PATTERNS = [
    re.compile(r"\b\d{2}/\d{2}/\d{4}\b"),   # DD/MM/YYYY
    re.compile(r"\b\d{2}-\d{2}-\d{4}\b"),   # DD-MM-YYYY
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),   # YYYY-MM-DD
    re.compile(r"\b\d{1,2}\s+\w+\s+\d{4}\b"),  # 1 January 2025
]

# Keywords that precede an expiry date on a document
_EXPIRY_KEYWORDS = [
    "expiry", "expires", "expiration",
    "valid until", "valid till", "valid to",
    "exp date", "date of expiry", "exp.",
]

# Keywords that precede a date of birth
_DOB_KEYWORDS = [
    "date of birth", "dob", "birth date", "born", "d.o.b",
]

# Lowercase tokens that indicate an NER "PERSON" entity is actually a
# document field label, not a real name.
# Context: Ukrainian (and other) bilingual passports print field labels in
# both Cyrillic and Latin script, e.g. "Номер паспорта / Passport Number".
# Tesseract reads Cyrillic Н/о/м/е/р as Latin H/o/m/e/p (they are visually
# identical), so the OCR output becomes "Homep nacnopta / Passport" which
# BERT tags as a PER entity.  We catch this with two signals:
#   1. The "/" separator used in every bilingual label
#   2. Common document-field keyword tokens in the extracted string
_LABEL_KEYWORDS = frozenset({
    "passport", "number", "no", "date", "birth", "expiry", "expires",
    "nationality", "surname", "given", "names", "holder", "issued",
    "authority", "sex", "place", "valid", "until", "type", "code",
    "country", "personal", "identity", "card", "document", "republic",
    "ukraine", "serial", "issued", "authority", "gender",
})


def _is_label_noise(name: str) -> bool:

    if "/" in name or "\\" in name:
        return True
    tokens = set(re.sub(r"[^a-z ]", "", name.lower()).split())
    return bool(tokens & _LABEL_KEYWORDS)


def extract_document_specific_entities(
    text: str,
    doc_type: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:

    entities: Dict[str, List[Dict[str, Any]]] = {
        "names": [],
        "id_numbers": [],
        "dates": [],
        "emails": [],
        "phone_numbers": [],
        "addresses": [],
    }

    logger.info(
        "[NER] Starting entity extraction — doc_type=%r  text_len=%d  "
        "transformers_available=%s  spacy_available=%s",
        doc_type, len(text), _TRANSFORMERS_AVAILABLE, _SPACY_AVAILABLE,
    )
    logger.info("[NER] OCR text (first 500 chars): %r", text[:500])

    # Strip Cyrillic from the text fed to NER models only.
    # Bilingual passports (Ukrainian, Russian, etc.) print every field label
    # in both Cyrillic and Latin script.  Even when Tesseract converts Cyrillic
    # lookalikes to ASCII, any remaining true Cyrillic chars confuse BERT/spaCy
    # into tagging field labels as person entities.  The original `text` is
    # preserved for MRZ parsing and the full-text token fallback.
    ner_text = _strip_cyrillic(text)
    if len(ner_text) != len(text):
        logger.info(
            "[NER] Stripped %d Cyrillic chars before NER; ner_text_len=%d",
            len(text) - len(ner_text), len(ner_text),
        )

    #Names (from transformers if available, otherwise spaCy)
    transformer_ents = extract_entities_with_transformers(ner_text)
    spacy_ents = extract_entities_with_spacy(ner_text)

    logger.info(
        "[NER] Transformer raw entities (%d): %s",
        len(transformer_ents),
        [(e["entity_type"], e["text"], round(e.get("confidence", 0), 3)) for e in transformer_ents],
    )
    logger.info(
        "[NER] spaCy raw entities (%d): %s",
        len(spacy_ents),
        [(e["entity_type"], e["text"]) for e in spacy_ents],
    )

    all_model_ents = combine_entity_results(transformer_ents, spacy_ents)

    for ent in all_model_ents:
        if ent["entity_type"] in ("PER", "PERSON"):
            if _is_label_noise(ent["text"]):
                logger.info(
                    "[NER] Discarding label-noise entity: %r  (type=%s  conf=%.2f)",
                    ent["text"], ent["entity_type"], ent.get("confidence", 0),
                )
                continue
            conf = ent.get("confidence", 0.85)
            if conf < 0.75:
                logger.info(
                    "[NER] Discarding low-confidence PER entity: %r  (conf=%.2f < 0.75)",
                    ent["text"], conf,
                )
                continue
            entities["names"].append({
                "value": ent["text"],
                "confidence": conf,
            })

    logger.info(
        "[NER] After model pass: %d PERSON name(s) found: %s",
        len(entities["names"]),
        [n["value"] for n in entities["names"]],
    )

    # If NER found no names, try to extract from MRZ (common for passport scans)
    if not entities["names"]:
        logger.info("[NER] No names from models — attempting MRZ parse")
        mrz = parse_mrz(text)
        if mrz and mrz.get("full_name"):
            entities["names"].append({
                "value": mrz["full_name"],
                "confidence": 0.95,
                "source": "mrz",
            })
            logger.info(
                "[NER] MRZ name fallback succeeded: full_name=%r  dob=%s  expiry=%s",
                mrz["full_name"], mrz.get("date_of_birth"), mrz.get("expiry_date"),
            )
            # Also inject MRZ dates so expiry/DOB checks can use them
            if mrz.get("date_of_birth") and not any(
                d["value"] == mrz["date_of_birth"] for d in entities["dates"]
            ):
                entities["dates"].append({"value": mrz["date_of_birth"], "confidence": 0.95, "source": "mrz_dob"})
            if mrz.get("expiry_date") and not any(
                d["value"] == mrz["expiry_date"] for d in entities["dates"]
            ):
                entities["dates"].append({"value": mrz["expiry_date"], "confidence": 0.95, "source": "mrz_expiry"})
        else:
            logger.info(
                "[NER] MRZ parse failed — no MRZ pattern found in text. "
                "First 300 chars: %r", text[:300],
            )

    #ID numbers (regex)
    id_patterns = {
        "pps_number": _PATTERN_PPS,
        "passport": _PATTERN_PASSPORT,
        "student_id": _PATTERN_STUDENT_ID,
    }
    for id_type, pattern in id_patterns.items():
        for match in pattern.finditer(text):
            entities["id_numbers"].append({
                "value": match.group(),
                "type": id_type,
                "confidence": 1.0,
            })

    #Dates (regex)
    seen_dates: set = set()
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            date_str = match.group()
            if date_str not in seen_dates:
                seen_dates.add(date_str)
                entities["dates"].append({"value": date_str, "confidence": 1.0})

    #Emails (regex)
    for email in _PATTERN_EMAIL.findall(text):
        entities["emails"].append({"value": email, "confidence": 1.0})

    #Phone numbers (regex)
    for phone in _PATTERN_PHONE.findall(text):
        entities["phone_numbers"].append({
            "value": phone.strip(),
            "confidence": 0.9,
        })

    return entities

def _parse_date_string(date_str: str) -> Optional[str]:

    try:
        from dateutil import parser as _du_parser  # type: ignore
        return _du_parser.parse(date_str, dayfirst=True).date().isoformat()
    except Exception:
        pass

    import datetime
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _find_nearest_date(
    text: str,
    keywords: List[str],
    dates: List[Dict[str, Any]],
    max_distance: int = 120,
) -> Optional[Dict[str, Any]]:

    text_lower = text.lower()

    keyword_positions: List[int] = []
    for kw in keywords:
        pos = text_lower.find(kw)
        if pos != -1:
            keyword_positions.append(pos + len(kw))

    if not keyword_positions:
        return None

    best: Optional[Dict[str, Any]] = None
    min_dist = float("inf")

    for date_entry in dates:
        date_pos = text.find(date_entry["value"])
        if date_pos == -1:
            continue
        for kw_end in keyword_positions:
            dist = abs(date_pos - kw_end)
            if dist < min_dist and dist <= max_distance:
                min_dist = dist
                best = date_entry

    return best


def extract_expiry_date(
    text: str,
    extracted_entities: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:

    dates = extracted_entities.get("dates", [])
    best = _find_nearest_date(text, _EXPIRY_KEYWORDS, dates)

    if best is None:
        return {"expiry_date": None, "expiry_date_str": None, "confidence": 0.0}

    parsed = _parse_date_string(best["value"])
    return {
        "expiry_date": parsed,
        "expiry_date_str": best["value"],
        "confidence": best.get("confidence", 1.0) if parsed else 0.0,
    }


def extract_date_of_birth(
    text: str,
    extracted_entities: Dict[str, List[Dict[str, Any]]],
) -> Optional[str]:

    dates = extracted_entities.get("dates", [])
    best = _find_nearest_date(text, _DOB_KEYWORDS, dates)
    if best is None:
        return None
    return _parse_date_string(best["value"])
