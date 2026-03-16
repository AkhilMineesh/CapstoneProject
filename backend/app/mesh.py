from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from .settings import settings


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")


def _load_cache(path: Path) -> dict[str, list[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(path: Path, cache: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _extract_candidate_terms(query: str) -> list[str]:
    q = " ".join(_WORD_RE.findall(query))
    q = re.sub(r"\b(latest|treatment|therapy|studies|published|after|before|stage|early)\b", "", q, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip()
    terms = []
    if q:
        terms.append(q)
    # Add a couple of longer tokens as fallback
    tokens = [t for t in q.split(" ") if len(t) >= 5]
    tokens = tokens[:2]
    terms.extend(tokens)
    # de-dupe preserving order
    out: list[str] = []
    seen = set()
    for t in terms:
        key = t.lower()
        if key not in seen:
            out.append(t)
            seen.add(key)
    return out[:3]


async def _mesh_titles_for_term(term: str, client: httpx.AsyncClient) -> list[str]:
    # 1) search descriptors
    r = await client.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "mesh", "term": term, "retmode": "json", "retmax": str(settings.mesh_max_terms)},
        timeout=20.0,
    )
    r.raise_for_status()
    data = r.json()
    ids = (data.get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []

    # 2) fetch titles
    r2 = await client.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "mesh", "id": ",".join(ids), "retmode": "json"},
        timeout=20.0,
    )
    r2.raise_for_status()
    d2 = r2.json()
    result = d2.get("result") or {}
    titles: list[str] = []
    for mid in ids:
        obj = result.get(mid) or {}
        title = obj.get("ds_meshterms") or obj.get("title")
        if isinstance(title, str) and title.strip():
            titles.append(title.strip())
    return titles[: settings.mesh_max_terms]


@dataclass(frozen=True)
class MeshExpansion:
    expanded_terms: list[str]
    expanded_query_text: str


async def expand_with_mesh(query: str) -> MeshExpansion:
    if not settings.mesh_expand:
        return MeshExpansion(expanded_terms=[], expanded_query_text=query)

    cache = _load_cache(settings.mesh_cache_path)
    candidates = _extract_candidate_terms(query)

    expanded: list[str] = []
    async with httpx.AsyncClient(headers={"User-Agent": "MedRAG/0.1"}) as client:
        for term in candidates:
            key = term.lower()
            titles = cache.get(key)
            if titles is None:
                try:
                    titles = await _mesh_titles_for_term(term, client)
                except Exception:  # noqa: BLE001
                    titles = []
                cache[key] = titles
            expanded.extend(titles or [])

    # keep unique and short
    uniq: list[str] = []
    seen = set()
    for t in expanded:
        k = t.lower()
        if k not in seen:
            uniq.append(t)
            seen.add(k)
    uniq = uniq[: settings.mesh_max_terms]

    _save_cache(settings.mesh_cache_path, cache)
    expanded_query_text = (query + " " + " ".join(uniq)).strip() if uniq else query
    return MeshExpansion(expanded_terms=uniq, expanded_query_text=expanded_query_text)
