from __future__ import annotations

import re


_POLITE_PREFIX_RE = re.compile(
    r"^\s*(?:please\s+)?(?:can|could|would|will|do)\s+you\s+(?:please\s+)?",
    flags=re.I,
)

_LEADING_INTENT_RE = re.compile(
    r"^\s*(?:i\s+(?:need|want|would\s+like|wish)\s+you\s+to|help\s+me\s+|show\s+me\s+|find\s+|retrieve\s+|get\s+|search\s+for\s+)",
    flags=re.I,
)

_WRAPPER_PHRASES = [
    r"\b(?:articles?|papers?|studies|literature|evidence)\s+(?:on|about|regarding|for)\b",
    r"\b(?:about|regarding)\b",
    r"\b(?:please|kindly|thanks|thank\s+you)\b",
]

_MULTI_WS_RE = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    return _MULTI_WS_RE.sub(" ", (text or "").strip())


def normalize_user_query(query: str) -> str:
    """
    Convert casual user phrasing into retrieval-oriented biomedical query text.

    Examples:
      - "I need you to retrieve articles on cancer" -> "cancer"
      - "Can you find papers about mRNA vaccines after 2022" -> "mRNA vaccines after 2022"
    """
    q = _normalize_ws(query)
    if not q:
        return ""

    # Keep year/time constraints exactly as expressed.
    year_constraints = re.findall(r"\b(?:after|since|before|prior\s+to|published\s+in|in)\s+(?:19|20)\d{2}\b", q, flags=re.I)

    cleaned = q
    for _ in range(3):
        nxt = _POLITE_PREFIX_RE.sub("", cleaned)
        nxt = _LEADING_INTENT_RE.sub("", nxt)
        nxt = re.sub(r"^\s*(?:retrieve|find|get|search(?:\s+for)?|show\s+me)\s+", "", nxt, flags=re.I)
        if nxt == cleaned:
            break
        cleaned = nxt

    for pat in _WRAPPER_PHRASES:
        cleaned = re.sub(pat, " ", cleaned, flags=re.I)

    cleaned = re.sub(r"^[\s:,.!?-]+|[\s:,.!?-]+$", "", cleaned)
    cleaned = _normalize_ws(cleaned)

    # If everything got stripped, fall back safely.
    if not cleaned:
        cleaned = q

    # Re-attach temporal constraints if they were dropped by wrapper cleanup.
    lower_cleaned = cleaned.lower()
    for yc in year_constraints:
        if yc.lower() not in lower_cleaned:
            cleaned = f"{cleaned} {yc}".strip()

    return _normalize_ws(cleaned)

