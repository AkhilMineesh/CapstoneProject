from __future__ import annotations

import re
from dataclasses import dataclass


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")


@dataclass(frozen=True)
class Snippet:
    text: str
    why: str


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def pick_evidence_snippets(abstract: str, query: str, max_snippets: int = 3) -> list[Snippet]:
    if not abstract:
        return []
    sentences = [s.strip() for s in _SENT_SPLIT.split(abstract) if s.strip()]
    if not sentences:
        return []

    qtok = _tokenize(query)
    scored: list[tuple[float, str]] = []
    for s in sentences:
        stok = _tokenize(s)
        overlap = len(qtok & stok)
        if overlap == 0:
            continue
        score = overlap / math.sqrt(len(stok) + 1e-6)
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)

    out: list[Snippet] = []
    for score, s in scored[:max_snippets]:
        out.append(Snippet(text=s, why=f"Token overlap score={score:.2f}"))
    return out


import math  # noqa: E402  (tiny local import to keep top-of-file tidy)
