from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")


@dataclass(frozen=True)
class GuardrailResult:
    warnings: list[str]


def validate_medical_terminology(conn: sqlite3.Connection, query: str) -> GuardrailResult:
    tokens = [t.lower() for t in _TOKEN_RE.findall(query)]
    if not tokens:
        return GuardrailResult(warnings=["Query contains no searchable terms."])

    # Build a lightweight vocabulary from MeSH/keywords observed in the corpus.
    cur = conn.execute(
        """
        SELECT mesh_terms_json, keywords_json
        FROM papers
        WHERE mesh_terms_json IS NOT NULL OR keywords_json IS NOT NULL
        LIMIT 5000
        """
    )
    vocab: set[str] = set()
    for row in cur:
        for col in ("mesh_terms_json", "keywords_json"):
            raw = row[col]
            if not raw:
                continue
            # raw is JSON array string, but avoid full json.loads overhead for guardrail:
            # pull out word-like substrings.
            vocab.update([t.lower() for t in _TOKEN_RE.findall(raw)])

    medical_hits = sum(1 for t in tokens if t in vocab)
    warnings: list[str] = []
    if medical_hits == 0 and len(tokens) >= 3:
        warnings.append(
            "Query has low medical-term coverage against the indexed corpus; consider adding disease/treatment terms."
        )
    if re.search(r"\b(should i take|my symptoms|diagnose me|am i)\b", query, flags=re.I):
        warnings.append("This tool provides research retrieval, not personalized medical advice.")
    return GuardrailResult(warnings=warnings)
