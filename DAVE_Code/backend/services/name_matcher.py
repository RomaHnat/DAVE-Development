from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Tokens that appear in the form name but should not be required to match
# (initials, common suffixes/prefixes). Matching the full surname plus at
# least one given-name token is enough to claim a match.
_DROPPABLE_TOKENS = {"jr", "sr", "ii", "iii", "iv", "mr", "mrs", "ms", "miss", "dr", "prof"}


def _strip_accents(value: str) -> str:
    if not value:
        return ""
    nfkd = unicodedata.normalize("NFKD", value)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalise_name(value: str) -> str:
    """Lowercase, strip accents, drop punctuation, collapse whitespace."""
    if not value:
        return ""
    cleaned = _strip_accents(value).lower()
    # Replace any non-alphanumeric character with whitespace
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def _tokens(value: str) -> List[str]:
    return [t for t in normalise_name(value).split() if t and t not in _DROPPABLE_TOKENS]


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + (0 if ca == cb else 1)))
        prev = curr
    return prev[-1]


def _max_edits_for(token: str) -> int:
    # Allow ~1 OCR error per 5 chars, with a floor of 1 so short tokens
    # ("Roma" vs "Rema") aren't rejected on a single substitution.
    return max(1, len(token) // 5)


def _token_aligns(form_token: str, candidates: Iterable[str], min_ratio: float) -> Tuple[bool, float]:
    best = 0.0
    matched = False
    max_edits = _max_edits_for(form_token)
    for cand in candidates:
        r = _ratio(form_token, cand)
        if r > best:
            best = r
        if r >= min_ratio or _edit_distance(form_token, cand) <= max_edits:
            matched = True
    return matched, best


def _best_token_ratio(token: str, candidates: Iterable[str]) -> float:
    best = 0.0
    for cand in candidates:
        r = _ratio(token, cand)
        if r > best:
            best = r
    return best


def name_match(
    form_name: str,
    doc_name: str,
    min_token_ratio: float = 0.85,
) -> Tuple[bool, float]:

    form_tokens = _tokens(form_name)
    doc_tokens = _tokens(doc_name)
    if not form_tokens or not doc_tokens:
        return False, 0.0

    # Exact normalised match (any order)
    if set(form_tokens) == set(doc_tokens):
        return True, 1.0

    # Per-token best-fuzzy match: every form token must align to *some*
    # doc token at >= min_token_ratio. Skip 1-character form tokens
    # (initials) — they're allowed to drop out.
    significant = [t for t in form_tokens if len(t) >= 2]
    if not significant:
        return False, 0.0

    per_token_results = [_token_aligns(t, doc_tokens, min_token_ratio) for t in significant]
    per_token_scores = [score for _, score in per_token_results]
    if all(matched for matched, _ in per_token_results):
        return True, sum(per_token_scores) / len(per_token_scores)

    # Whole-string fuzzy as a last resort (handles concatenated names)
    whole = _ratio(" ".join(sorted(form_tokens)), " ".join(sorted(doc_tokens)))
    if whole >= 0.92:
        return True, whole

    return False, max(whole, sum(per_token_scores) / len(per_token_scores))


def best_name_match(
    form_name: str,
    candidate_names: Iterable[str],
    min_token_ratio: float = 0.85,
) -> Tuple[Optional[str], float, bool]:

    best_score = 0.0
    best_candidate: Optional[str] = None
    matched = False
    for cand in candidate_names:
        if not cand:
            continue
        is_match, score = name_match(form_name, cand, min_token_ratio=min_token_ratio)
        if score > best_score:
            best_score = score
            best_candidate = cand
        if is_match:
            matched = True
    return best_candidate, best_score, matched


def all_form_tokens_in_text(form_name: str, text: str, min_token_ratio: float = 0.85) -> bool:

    significant_form_tokens = [t for t in _tokens(form_name) if len(t) >= 3]
    if not significant_form_tokens:
        logger.warning(
            "[name_matcher] all_form_tokens_in_text: no significant tokens in form_name=%r",
            form_name,
        )
        return False
    text_tokens = [t for t in normalise_name(text).split() if len(t) >= 2]
    if not text_tokens:
        logger.warning(
            "[name_matcher] all_form_tokens_in_text: no tokens extracted from text "
            "(text_len=%d)", len(text),
        )
        return False

    token_results = []
    for form_token in significant_form_tokens:
        hit, best_score = _token_aligns(form_token, text_tokens, min_token_ratio)
        token_results.append((form_token, hit, round(best_score, 3)))

    logger.info(
        "[name_matcher] all_form_tokens_in_text — form=%r  "
        "significant_tokens=%s  per_token_results=%s  "
        "text_token_count=%d  overall=%s",
        form_name,
        significant_form_tokens,
        token_results,
        len(text_tokens),
        all(hit for _, hit, _ in token_results),
    )

    return all(hit for _, hit, _ in token_results)
