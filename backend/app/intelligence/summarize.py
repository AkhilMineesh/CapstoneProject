from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from .clinical_reasoning import generate_clinical_reasoning


_POS_RE = re.compile(r"\b(improv(ed|ement)|benefit(ed)?|reduc(ed|tion)|increas(ed|e)\s+survival)\b", re.I)
_NEG_RE = re.compile(r"\b(wors(e|ened)|harm(ed)?|increas(ed|e)\s+(pain|mortality))\b", re.I)
_NEU_RE = re.compile(r"\b(no\s+significant|did\s+not\s+(improve|reduce)|no\s+difference)\b", re.I)


def _stance(text: str) -> str:
    if _NEU_RE.search(text):
        return "neutral"
    if _NEG_RE.search(text):
        return "negative"
    if _POS_RE.search(text):
        return "positive"
    return "unknown"


def _outcome_tags(text: str) -> list[str]:
    tags = []
    t = (text or "").lower()
    for kw in ("overall survival", "progression-free survival", "mortality", "pain", "function", "quality of life"):
        if kw in t:
            tags.append(kw)
    return tags or ["primary outcome"]


def build_trends(results: list[dict[str, Any]], top_n: int = 8) -> list[dict[str, Any]]:
    by_year_term: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        year = (r.get("citation") or {}).get("year")
        if year is None:
            continue
        terms: list[str] = []
        terms.extend((r.get("keywords") or [])[:5])
        terms.extend((r.get("mesh_terms") or [])[:5])
        for t in terms:
            key = (t or "").strip()
            if not key or len(key) < 4:
                continue
            by_year_term[key][int(year)] += 1

    totals = Counter({term: sum(yrs.values()) for term, yrs in by_year_term.items()})
    out: list[dict[str, Any]] = []
    for term, _ in totals.most_common(top_n):
        out.append({"term": term, "counts_by_year": dict(sorted(by_year_term[term].items()))})
    return out


def build_conflicts(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        abstract = r.get("abstract") or ""
        st = _stance(abstract)
        for ot in _outcome_tags(abstract):
            buckets[ot][st].append(r.get("pmid") or "")

    conflicts: list[dict[str, Any]] = []
    for outcome, stances in buckets.items():
        pos = stances.get("positive") or []
        neu = stances.get("neutral") or []
        neg = stances.get("negative") or []
        if (pos and neu) or (pos and neg) or (neu and neg):
            conflicts.append(
                {
                    "outcome": outcome,
                    "papers_supporting": [p for p in pos if p],
                    "papers_conflicting": [p for p in (neu + neg) if p],
                    "note": "Detected mixed abstract-level outcome language; verify full text and endpoints.",
                }
            )
    return conflicts[:5]


def build_knowledge_graph(results: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], int] = defaultdict(int)

    def upsert_node(node_id: str, label: str, kind: str):
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "kind": kind, "count": 0}
        nodes[node_id]["count"] += 1

    def add_edge(src: str, dst: str, rel: str):
        edges[(src, dst, rel)] += 1

    outcome_vocab = {
        "overall survival": "overall survival",
        "progression-free survival": "progression-free survival",
        "mortality": "mortality",
        "pain": "pain",
        "function": "function",
        "quality of life": "quality of life",
    }
    treatment_markers = ("therapy", "treatment", "vaccine", "surgery", "inhibitor", "arthroplasty", "ablation")

    for r in results:
        disease = (r.get("disease_area") or "").strip()
        if disease:
            did = f"disease:{disease.lower()}"
            upsert_node(did, disease, "disease")
        else:
            did = "disease:unspecified"
            upsert_node(did, "Unspecified disease area", "disease")

        abs_l = (r.get("abstract") or "").lower()
        outcomes = [v for k, v in outcome_vocab.items() if k in abs_l] or ["primary outcome"]
        for o in outcomes:
            oid = f"outcome:{o}"
            upsert_node(oid, o, "outcome")
            add_edge(did, oid, "studies")

        candidates: list[str] = []
        candidates.extend((r.get("keywords") or [])[:10])
        candidates.extend((r.get("mesh_terms") or [])[:10])
        for c in candidates:
            cl = (c or "").lower()
            if not cl:
                continue
            if any(m in cl for m in treatment_markers) or "drug" in cl or "chemotherapy" in cl or "radiotherapy" in cl:
                tid = f"treatment:{cl}"
                upsert_node(tid, c, "treatment")
                add_edge(did, tid, "treated_by")
                for o in outcomes:
                    add_edge(tid, f"outcome:{o}", "affects")

    node_list = list(nodes.values())
    edge_list = [{"source": s, "target": t, "rel": rel, "weight": w} for (s, t, rel), w in edges.items()]
    return {"nodes": node_list[:120], "edges": edge_list[:220]}


def summarize_insights(
    query: str,
    expanded_query: str | None,
    results: list[dict[str, Any]],
    guardrails: list[str],
) -> dict[str, Any]:
    if not results:
        return {
            "summary": "No matching papers found for the given query and filters.",
            "key_findings": [],
            "conflicts": [],
            "trends": [],
            "knowledge_graph": None,
            "guardrails": guardrails,
            "expanded_query": expanded_query,
        }

    findings: list[str] = []
    for r in results[:5]:
        title = (r.get("title") or "").strip()
        pmid = r.get("pmid") or ""
        year = (r.get("citation") or {}).get("year") or "n.d."
        evidence = r.get("evidence") or []
        if evidence:
            findings.append(f"{title} ({year}, PMID {pmid}): {(evidence[0] or {}).get('text')}")
        else:
            findings.append(f"{title} ({year}, PMID {pmid}).")
        if len(findings) >= 5:
            break

    summary = f"Retrieved {len(results)} papers for: {query}."
    clinical_reasoning = None
    clinical_limitations: list[str] = []
    try:
        clinical_reasoning = generate_clinical_reasoning(query=query, results=results, guardrails=guardrails)
    except Exception as e:  # noqa: BLE001
        # Keep baseline behavior if the model call fails.
        clinical_reasoning = None
        clinical_limitations.append(f"OpenAI clinical reasoning fallback used due to upstream error: {type(e).__name__}.")

    if clinical_reasoning:
        if clinical_reasoning.get("summary"):
            summary = str(clinical_reasoning["summary"]).strip()
        cr_findings = clinical_reasoning.get("key_findings")
        if isinstance(cr_findings, list) and cr_findings:
            findings = [str(x) for x in cr_findings if str(x).strip()][:8]
        cr_limits = clinical_reasoning.get("limitations")
        if isinstance(cr_limits, list):
            clinical_limitations.extend([str(x) for x in cr_limits if str(x).strip()])

    return {
        "summary": summary,
        "key_findings": findings,
        "conflicts": build_conflicts(results),
        "trends": build_trends(results),
        "knowledge_graph": build_knowledge_graph(results),
        "guardrails": guardrails,
        "expanded_query": expanded_query,
        "clinical_limitations": clinical_limitations,
        "clinical_reasoning_model": (clinical_reasoning or {}).get("model"),
    }
