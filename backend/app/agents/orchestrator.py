from __future__ import annotations

import json
import re
from typing import Any

from ..db import db_conn, migrate
from ..intelligence.summarize import summarize_insights
from ..mesh import expand_with_mesh
from ..retrieval.guardrails import validate_medical_terminology
from ..retrieval.hybrid import hybrid_retrieve
from ..settings import settings


_N_RE = re.compile(r"\b(n\s*=\s*\d{2,6}|\b\d{2,6}\s+patients?)\b", re.I)
_P_RE = re.compile(r"\b(p\s*[<=>]\s*0\.\d+|confidence interval|hazard ratio|odds ratio|relative risk)\b", re.I)


def _agent(agent: str, notes: list[str]) -> dict[str, Any]:
    return {"agent": agent, "notes": notes}


def _infer_filters_from_query(query: str) -> dict[str, Any] | None:
    """
    Lightweight metadata parsing from natural language queries.

    Examples:
      - "mRNA vaccine studies published after 2022" -> publication_year_from=2023
      - "papers before 2018" -> publication_year_to=2017
    """
    q = query.lower()
    y_from = None
    y_to = None

    m = re.search(r"\b(after|since)\s+(19|20)\d{2}\b", q)
    if m:
        y = int(m.group(0).split()[-1])
        y_from = y + 1 if "after" in m.group(1) else y

    m = re.search(r"\b(before|prior to)\s+(19|20)\d{2}\b", q)
    if m:
        y = int(m.group(0).split()[-1])
        y_to = y - 1

    # "published in 2022" or just "in 2022" (only if "published" is present to avoid false positives)
    m = re.search(r"\bpublished\s+(in|during)\s+(19|20)\d{2}\b", q)
    if m:
        y = int(m.group(0).split()[-1])
        y_from = y
        y_to = y

    if y_from is None and y_to is None:
        return None
    out: dict[str, Any] = {}
    if y_from is not None:
        out["publication_year_from"] = y_from
    if y_to is not None:
        out["publication_year_to"] = y_to
    return out


def _methodology_critic(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return _agent("methodology_critic", ["No papers to critique (empty result set)."])
    rcts = sum(
        1 for r in results if any("randomized" in (pt or "").lower() for pt in (r.get("publication_types") or []))
    )
    trials = sum(
        1
        for r in results
        if any("clinical trial" in (pt or "").lower() for pt in (r.get("publication_types") or []))
    )
    reviews = sum(
        1 for r in results if any("review" in (pt or "").lower() for pt in (r.get("publication_types") or []))
    )
    notes = [
        f"Study types detected (from PubMed publication types): RCT={rcts}, clinical trials={trials}, reviews={reviews}.",
        "Methodology flags are heuristic and based on abstracts/metadata only.",
    ]
    return _agent("methodology_critic", notes)


def _statistical_reviewer(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return _agent("statistical_reviewer", ["No papers to review (empty result set)."])
    with_n = sum(1 for r in results if _N_RE.search(r.get("abstract") or ""))
    with_stats = sum(1 for r in results if _P_RE.search(r.get("abstract") or ""))
    notes = [
        f"Abstracts mentioning sample size: {with_n}/{len(results)}.",
        f"Abstracts mentioning p-values/effect measures: {with_stats}/{len(results)}.",
    ]
    if with_stats == 0:
        notes.append("No statistical signals found in the top abstracts; consider checking full text for endpoints and effect sizes.")
    return _agent("statistical_reviewer", notes)


def _clinical_applicability(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return _agent("clinical_applicability", ["No papers to assess (empty result set)."])
    pop_markers = ("adult", "children", "pediatric", "elderly", "women", "men", "randomized", "double-blind")
    mentions = sum(1 for r in results if any(m in (r.get("abstract") or "").lower() for m in pop_markers))
    notes = [
        f"Abstracts with basic population/design markers: {mentions}/{len(results)}.",
        "Applicability requires checking inclusion/exclusion criteria and clinical context; abstracts are insufficient for decisions.",
    ]
    return _agent("clinical_applicability", notes)


def run_multi_agent_analysis(req: dict[str, Any]) -> dict[str, Any]:
    query = (req.get("query") or "").strip()
    if not query:
        raise ValueError("Missing required field: query")

    top_k = int(req.get("top_k") or settings.final_top_k)
    rerank = bool(req.get("rerank", True))
    include_insights = bool(req.get("include_insights", True))
    filters = req.get("filters") if isinstance(req.get("filters"), dict) else None
    if not filters:
        filters = _infer_filters_from_query(query)

    with db_conn(settings.db_path) as conn:
        migrate(conn)
        n = int(conn.execute("SELECT COUNT(1) AS c FROM papers").fetchone()["c"])
        if n == 0:
            raise ValueError("Index is empty. Ingest PubMed/MEDLINE abstracts first (see backend/scripts/ingest_pubmed.py).")
        emb_n = int(conn.execute("SELECT COUNT(1) AS c FROM embeddings").fetchone()["c"])

        mesh = None
        expanded_query = query
        if settings.mesh_expand:
            import asyncio

            mesh = asyncio.run(expand_with_mesh(query))
            expanded_query = mesh.expanded_query_text

        guard = validate_medical_terminology(conn, expanded_query)
        results = hybrid_retrieve(
            conn=conn,
            query=query,
            expanded_query=expanded_query,
            filters=filters,
            rerank=rerank,
            top_k=top_k,
        )

        insights = None
        if include_insights:
            insights = summarize_insights(
                query=query,
                expanded_query=expanded_query if expanded_query != query else None,
                results=results,
                guardrails=guard.warnings,
            )

        return {
            "query": query,
            "expanded_query": expanded_query if expanded_query != query else None,
            "results": results,
            "insights": insights,
            "guardrails": guard.warnings,
        }
