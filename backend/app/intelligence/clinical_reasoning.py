from __future__ import annotations

import json
from typing import Any

import httpx

from ..settings import settings


def _paper_payload(results: list[dict[str, Any]], max_papers: int = 6) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results[:max_papers]:
        citation = r.get("citation") or {}
        abstract = (r.get("abstract") or "").strip()
        evidence = r.get("evidence") or []
        out.append(
            {
                "pmid": r.get("pmid"),
                "title": r.get("title"),
                "year": citation.get("year"),
                "journal": citation.get("journal"),
                "publication_types": r.get("publication_types") or [],
                "evidence_snippets": [e.get("text") for e in evidence if isinstance(e, dict) and e.get("text")][:3],
                "abstract": abstract[:1000],
            }
        )
    return out


def generate_clinical_reasoning(
    query: str,
    results: list[dict[str, Any]],
    guardrails: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    LLM-based clinical interpretation over retrieved abstracts.
    Returns None if OpenAI key/model is unavailable.
    """
    if not settings.openai_api_key or not settings.openai_clinical_reasoning:
        return None
    if not results:
        return None

    payload = {
        "query": query,
        "guardrails": guardrails or [],
        "papers": _paper_payload(results),
        "task": (
            "Perform deep clinical reasoning strictly from the provided abstracts/evidence. "
            "Return JSON with keys: summary, findings, limitations. "
            "Each finding must include: claim, pmid, title, year, confidence "
            "(confidence must be one of high|moderate|low). "
            "Do not fabricate citations. Keep summary concise and clinically focused "
            "(benefits, harms, population fit, and applicability boundaries)."
        ),
    }

    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    timeout = httpx.Timeout(connect=15.0, read=settings.openai_reasoning_timeout_s, write=30.0, pool=15.0)
    with httpx.Client(base_url=settings.openai_base_url, headers=headers, timeout=timeout) as client:
        r = client.post(
            "/chat/completions",
            json={
                "model": settings.openai_reasoning_model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a cautious clinical research synthesizer. "
                            "Use only provided evidence. No hallucinated PMIDs."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload)},
                ],
            },
        )
        r.raise_for_status()
        data = r.json()

    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    obj = json.loads(content) if content else {}

    summary = str(obj.get("summary") or "").strip()
    findings = obj.get("findings") if isinstance(obj.get("findings"), list) else []
    limitations = obj.get("limitations") if isinstance(obj.get("limitations"), list) else []

    clean_findings: list[str] = []
    for item in findings[:8]:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        pmid = str(item.get("pmid") or "").strip()
        title = str(item.get("title") or "").strip()
        year = item.get("year")
        conf = str(item.get("confidence") or "").strip().lower()
        if conf not in ("high", "moderate", "low"):
            conf = "moderate"
        if not claim:
            continue
        ref = f"{title} ({year if year else 'n.d.'}, PMID {pmid})".strip()
        clean_findings.append(f"{ref}: {claim} [confidence: {conf}]")

    clean_limits: list[str] = []
    for l in limitations[:5]:
        s = str(l or "").strip()
        if s:
            clean_limits.append(s)

    if not summary and not clean_findings:
        return None

    return {
        "summary": summary,
        "key_findings": clean_findings,
        "limitations": clean_limits,
        "model": settings.openai_reasoning_model,
    }


