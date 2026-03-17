from __future__ import annotations

import re
from collections import Counter


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")


_STOP = {
    # Generic English stopwords (small set; keep dependency-free)
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "these",
    "those",
    "into",
    "onto",
    "over",
    "under",
    "between",
    "among",
    "within",
    "without",
    "such",
    "also",
    "may",
    "might",
    "can",
    "could",
    "should",
    "would",
    "will",
    "was",
    "were",
    "been",
    "are",
    "is",
    "as",
    "at",
    "by",
    "of",
    "to",
    "in",
    "on",
    "an",
    "a",
    "it",
    "its",
    "we",
    "our",
    "their",
    "they",
    "you",
    "your",
    # Common paper boilerplate
    "introduction",
    "background",
    "methods",
    "method",
    "materials",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "objective",
    "objectives",
    "aim",
    "aims",
    "study",
    "studies",
    "paper",
    "figure",
    "table",
    "supplementary",
    "copyright",
    "license",
    "doi",
    "et",
    "al",
}


def _normalize_ws(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _extract_section(text: str, heading: str, max_chars: int) -> str | None:
    # Look for a heading like "Abstract" and take the following chunk.
    m = re.search(rf"(?im)^\s*{re.escape(heading)}\s*[:\-]?\s*$", text)
    if not m:
        return None
    start = m.end()
    chunk = text[start : start + max_chars].strip()
    return chunk or None


def compact_query_from_text(text: str, *, max_chars: int = 8000) -> str:
    """
    Convert long document text into a compact retrieval query:
    - Prefer Abstract/Conclusion chunks when present
    - Add top keywords and keyphrases (bigrams)
    - Keep size bounded to avoid slow/noisy retrieval
    """
    t = _normalize_ws(text or "")
    if not t:
        return ""

    # Short documents: treat as a normal query.
    if len(t) <= max_chars:
        return t

    # Prefer Abstract / Conclusion if present.
    abstract = _extract_section(t, "Abstract", 3500) or ""
    conclusion = _extract_section(t, "Conclusion", 1500) or _extract_section(t, "Conclusions", 1500) or ""

    # Always keep a small excerpt from the beginning (often has title/context).
    excerpt = t[:2000]

    focus_text = "\n\n".join([x for x in (abstract, conclusion, excerpt) if x]).strip()

    words = [w.lower() for w in _WORD_RE.findall(focus_text)]
    words = [w for w in words if w not in _STOP and not re.fullmatch(r"(19|20)\d{2}", w)]
    if not words:
        return excerpt[:max_chars]

    freq = Counter(words)

    # Simple bigram keyphrases (skip stopwords and very rare terms).
    phrases: Counter[str] = Counter()
    for a, b in zip(words, words[1:], strict=False):
        if a in _STOP or b in _STOP:
            continue
        if freq[a] < 2 or freq[b] < 2:
            continue
        phrases[f"{a} {b}"] += 1

    top_terms = [w for w, _ in freq.most_common(14)]
    top_phrases = [p for p, _ in phrases.most_common(10)]

    query = (
        "Document-derived query.\n"
        f"EXCERPT:\n{excerpt.strip()}\n\n"
        + (f"ABSTRACT:\n{abstract.strip()}\n\n" if abstract else "")
        + (f"CONCLUSION:\n{conclusion.strip()}\n\n" if conclusion else "")
        + "KEYWORDS: "
        + ", ".join(top_terms)
        + "\n"
        + ("KEYPHRASES: " + "; ".join(top_phrases) + "\n" if top_phrases else "")
    ).strip()
    return query[:max_chars]

