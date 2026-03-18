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




def simple_query_from_text(text: str, *, max_terms: int = 6, max_chars: int = 180) -> str:
    """
    Build a short, human-readable query from extracted document/image text.
    Prefer broad natural phrasing over long keyword lists.
    """
    t = _normalize_ws(text or "")
    if not t:
        return ""

    lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
    first_line = lines[0] if lines else ""

    # If the first line already looks like a concise prompt/title, use it.
    if first_line and 4 <= len(first_line.split()) <= 14 and len(first_line) <= 90:
        q = first_line
        return re.sub(r"\s+", " ", q).strip()[:max_chars]

    words = [w.lower() for w in _WORD_RE.findall(t[:3000])]
    words = [w for w in words if w not in _STOP and not re.fullmatch(r"(19|20)\d{2}", w)]
    top_terms = [w for w, _ in Counter(words).most_common(max_terms)]

    canon_map = {
        "radiation": "radiotherapy",
        "radiotherapy": "radiotherapy",
        "tumor": "cancer",
        "tumors": "cancer",
        "cancers": "cancer",
    }
    generic = {
        "treatment",
        "therapy",
        "therapies",
        "study",
        "studies",
        "research",
        "analysis",
        "patient",
        "patients",
        "disease",
        "clinical",
    }

    seen: set[str] = set()
    terms: list[str] = []
    for w in top_terms:
        c = canon_map.get(w, w)
        if c in seen:
            continue
        seen.add(c)
        terms.append(c)

    domain_terms = [x for x in terms if x not in generic]

    if "cancer" in domain_terms:
        q = "Cancer treatment options"
    elif len(domain_terms) >= 2:
        q = f"Research on {domain_terms[0]} and {domain_terms[1]}"
    elif len(domain_terms) == 1:
        q = f"Research on {domain_terms[0]}"
    elif terms:
        q = f"Research on {terms[0]}"
    else:
        q = "Medical research summary"

    q = re.sub(r"\s+", " ", q).strip()
    if q:
        q = q[0].upper() + q[1:]
    return q[:max_chars]



def simple_query_from_audio_transcript(text: str, *, max_chars: int = 180) -> str:
    """
    Build a short query from a transcribed voice request.
    Returns empty string when transcript is too noisy/ambiguous to use.
    """
    t = _normalize_ws(text or "")
    if not t:
        return ""

    # Remove common speech fillers to improve usable intent extraction.
    filler = {
        "um", "uh", "hmm", "like", "you", "know", "basically", "actually", "please", "hey", "hi", "hello"
    }
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}", t)]
    words = [w for w in words if w not in filler]

    # Not enough meaningful content.
    if len(words) < 3:
        return ""

    # Try concise first sentence if it looks like a query.
    first = t.split(".")[0].strip()
    if 4 <= len(first.split()) <= 16:
        q = re.sub(r"\s+", " ", first).strip()
        return q[:max_chars]

    # Fall back to term-based simple query.
    q = simple_query_from_text(" ".join(words), max_terms=6, max_chars=max_chars)
    # Guard against very generic output.
    bad = {"medical research summary", "research summary", "medical research"}
    if q.strip().lower() in bad:
        return ""
    return q
