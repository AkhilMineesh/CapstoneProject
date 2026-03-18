from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Any
import re

from ..intelligence.evidence import pick_evidence_snippets
from ..settings import settings
from .models.registry import get_embedding_model_id
from .embedding import embed_texts
from .rerank import rerank_pairs
from .vector_index import vector_search_subset


@dataclass(frozen=True)
class HybridResult:
    pmid: str
    score: float


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "were",
    "with",
    # Query modifiers
    "latest",
    "treatment",
    "treatments",
    "therapy",
    "therapies",
    "studies",
    "study",
    "published",
    "after",
    "before",
    "early",
    "stage",
    "resectable",
    "localized",
    "option",
    "options",
}


def _expand_query_terms_for_overlap(q_terms: set[str]) -> set[str]:
    """
    Add a compact alias set for common biomedical phrasing variants.
    """
    out = set(q_terms)
    if "mrna" in out:
        out.update({"messenger", "rna"})
    if "vaccine" in out or "vaccines" in out:
        out.update({"vaccine", "vaccines", "vaccination", "vaccinations", "immunization", "immunizations"})
    if "arthritis" in out:
        out.update({"osteoarthritis"})
    return out


def _title_has_term(term: str, title_terms: set[str]) -> bool:
    t = (term or "").lower()
    if t == "mrna":
        return "mrna" in title_terms or ("messenger" in title_terms and "rna" in title_terms)
    if t in {"vaccine", "vaccines"}:
        return bool({"vaccine", "vaccines", "vaccination", "vaccinations", "immunization", "immunizations"} & title_terms)
    if t == "arthritis":
        return bool({"arthritis", "osteoarthritis"} & title_terms)
    return t in title_terms


def _focus_terms(query: str) -> list[str]:
    raw = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", query)]
    out: list[str] = []
    for t in raw:
        if t in _STOPWORDS:
            continue
        if len(t) < 3:
            continue
        # Handle "non-invasive" variants
        if t == "non":
            continue
        if t == "invasive":
            continue
        # Don't treat years as lexical constraints; they're better handled as metadata filters.
        if re.fullmatch(r"(19|20)\d{2}", t or ""):
            continue
        out.append(t)
    return out


def _keyword_search(conn: sqlite3.Connection, query: str, top_k: int) -> list[HybridResult]:
    terms = _focus_terms(query)

    # Build a small set of required concepts to avoid loose matches without returning 0 results.
    phrase = None
    # Prefer common biomedical bigrams as a phrase (e.g. "pancreatic cancer", "knee arthritis").
    anchors = {"cancer", "carcinoma", "neoplasm", "arthritis", "vaccine", "vaccines", "infection", "disease", "syndrome"}
    for i in range(len(terms) - 1):
        a, b = terms[i], terms[i + 1]
        if b in anchors:
            phrase = f"\"{a} {b}\""
            break

    required: list[str] = []
    if phrase:
        required.append(phrase)
    required.extend(terms[:4])
    required = [t for t in required if t]

    fts_query = " AND ".join(required[:8]) if required else query
    cur = conn.execute(
        """
        SELECT pmid, bm25(paper_fts) AS score
        FROM paper_fts
        WHERE paper_fts MATCH ?
        ORDER BY score
        LIMIT ?;
        """,
        (fts_query, int(top_k)),
    )
    out: list[HybridResult] = []
    for row in cur:
        # bm25: lower is better; invert to a positive score
        bm25 = float(row["score"])
        score = 1.0 / (1.0 + max(bm25, 0.0))
        out.append(HybridResult(pmid=row["pmid"], score=score))
    return out


def _must_title_terms(query: str) -> set[str]:
    """
    Heuristic: if the query contains a strong biomedical bigram (e.g. "pancreatic cancer"),
    require those core terms to appear in the title to improve precision.
    """
    terms = _focus_terms(query)
    anchors = {"cancer", "carcinoma", "neoplasm", "arthritis", "vaccine", "vaccines", "infection", "disease", "syndrome"}
    for i in range(len(terms) - 1):
        a, b = terms[i], terms[i + 1]
        if b in anchors:
            return {a, b}
    return set()


def _apply_filters(rows: list[sqlite3.Row], filters: dict | None) -> list[sqlite3.Row]:
    if not filters:
        return rows

    def ok(r: sqlite3.Row) -> bool:
        year = r["year"]
        y_from = filters.get("publication_year_from")
        y_to = filters.get("publication_year_to")
        journal = filters.get("journal")
        disease_area = filters.get("disease_area")
        stage = filters.get("clinical_trial_stage")
        study_type = filters.get("study_type")

        if y_from is not None and year is not None and int(year) < int(y_from):
            return False
        if y_to is not None and year is not None and int(year) > int(y_to):
            return False
        if journal and (r["journal"] or "").lower() != str(journal).lower():
            return False
        if disease_area and (r["disease_area"] or "").lower() != str(disease_area).lower():
            return False
        if stage and (r["trial_stage"] or "").lower() != str(stage).lower():
            return False
        if study_type:
            pub_types = json.loads(r["publication_types_json"] or "[]")
            st = str(study_type).lower()
            if not any(st in (pt or "").lower() for pt in pub_types):
                return False
        return True

    return [r for r in rows if ok(r)]


def _rrf_score(rank: int, k: int) -> float:
    return 1.0 / (k + rank)


def hybrid_retrieve(
    conn: sqlite3.Connection,
    query: str,
    expanded_query: str,
    filters: dict | None,
    rerank: bool,
    top_k: int,
) -> list[dict[str, Any]]:
    # 1) keyword + vector candidates
    kw_hits = _keyword_search(conn, expanded_query, settings.keyword_top_k)
    must_title = _must_title_terms(query)

    use_vectors = (settings.embeddings_provider or "").lower() != "hash"
    vec_hits = []
    vec_score_map: dict[str, float] = {}
    if use_vectors and kw_hits:
        qvec = embed_texts([expanded_query])[0]
        model_id = get_embedding_model_id()
        # Avoid full-table vector scans; only do vector similarity over the keyword candidate set.
        candidate_pmids = [h.pmid for h in kw_hits]
        vec_hits = vector_search_subset(
            conn,
            qvec,
            candidate_pmids,
            min(settings.vector_top_k, max(1, len(candidate_pmids))),
            model_id=model_id,
        )
        vec_score_map = {h.pmid: float(h.score) for h in vec_hits}

    # 2) combine via RRF
    kw_rank = {h.pmid: i + 1 for i, h in enumerate(kw_hits)}
    vec_rank = {h.pmid: i + 1 for i, h in enumerate(vec_hits)}
    all_pmids = set(kw_rank) | set(vec_rank)

    combined: list[tuple[str, float]] = []
    for pmid in all_pmids:
        score = 0.0
        if pmid in kw_rank:
            score += settings.weight_keyword * _rrf_score(kw_rank[pmid], settings.rrf_k)
        if pmid in vec_rank:
            score += settings.weight_vector * _rrf_score(vec_rank[pmid], settings.rrf_k)
        combined.append((pmid, score))
    combined.sort(key=lambda x: x[1], reverse=True)

    # 3) fetch metadata for top rerank set (filter at this stage)
    # When using hash embeddings (no real semantics), we rely more on keyword/metadata gating.
    # Pull a larger candidate pool so we can keep strict precision gates without returning too few results.
    pre_n = max(top_k, settings.rerank_top_k)
    if (settings.embeddings_provider or "").lower() == "hash":
        pre_n = max(pre_n, 120)
    pre_top = combined[:pre_n]
    if not pre_top:
        return []
    pmid_list = [p for p, _ in pre_top]
    placeholders = ",".join(["?"] * len(pmid_list))
    cur = conn.execute(
        f"""
        SELECT pmid,title,abstract,year,journal,authors_json,mesh_terms_json,keywords_json,publication_types_json,doi,
               disease_area,trial_stage
        FROM papers
        WHERE pmid IN ({placeholders})
        """,
        pmid_list,
    )
    by_pmid: dict[str, sqlite3.Row] = {r["pmid"]: r for r in cur.fetchall()}
    ordered_rows = [by_pmid[p] for p in pmid_list if p in by_pmid]
    ordered_rows = _apply_filters(ordered_rows, filters)
    filters_active = bool(filters)
    allowed_pmids = {r["pmid"] for r in ordered_rows}

    # 4) optional cross-encoder re-ranking
    rescored: list[tuple[str, float]] = []
    rerank_n = min(settings.rerank_top_k, max(top_k * 2, 10))
    if rerank and ordered_rows:
        try:
            passages = [f"{r['title']}\n\n{r['abstract']}" for r in ordered_rows[: rerank_n]]
            ce_scores = rerank_pairs(query, passages)
            if len(ce_scores) != len(passages) or not ce_scores:
                raise RuntimeError("Reranker unavailable or returned unexpected scores.")
            for r, s in zip(ordered_rows[: rerank_n], ce_scores, strict=False):
                rescored.append((r["pmid"], float(s)))
            # Keep the rest by hybrid score
            kept = {pmid for pmid, _ in rescored}
            base_score = {pmid: sc for pmid, sc in combined}
            for r in ordered_rows[rerank_n :]:
                rescored.append((r["pmid"], float(base_score.get(r["pmid"], 0.0))))
            rescored.sort(key=lambda x: x[1], reverse=True)
        except Exception:  # noqa: BLE001
            rescored = combined
    else:
        rescored = combined

    # 5) build API results
    results: list[dict[str, Any]] = []
    base_score_map = {pmid: sc for pmid, sc in combined}
    # Use the original query for overlap gating; expanded_query can include MeSH terms that add noise.
    q_terms = _expand_query_terms_for_overlap(set(_focus_terms(query)))
    # If the query includes specific stage qualifiers, require more overlap to improve exactness.
    q_lower = query.lower()
    required_overlap = settings.min_query_term_overlap
    if re.search(r"\bstage\s*(i{1,3}|iv|1|2|3|4)\b", q_lower) or "resectable" in q_lower or "localized" in q_lower:
        required_overlap = max(required_overlap, 3)

    wants_intervention = bool(re.search(r"\b(treatment|treatments|therapy|therap(y|ies)|management)\b", q_lower))
    wants_noninvasive = bool(re.search(r"\b(non[-\\s]?invasive|conservative)\b", q_lower))
    intervention_strong_markers = {
        "drug",
        "randomized",
        "phase",
        "regimen",
        "injection",
        "analgesic",
        "surgery",
        "resection",
        "neoadjuvant",
        "adjuvant",
        "chemotherapy",
        "radiotherapy",
        "immunotherapy",
        "targeted",
        "ablation",
        "palliative",
        "palliation",
        "operation",
        "stent",
        "physical",
        "exercise",
        "rehabilitation",
    }
    intervention_soft_markers = {"review", "systematic", "meta", "guideline", "consensus"}
    intervention_core_markers = {
        "therapy",
        "therapeutic",
        "treatment",
        "treat",
        "treated",
        "treating",
        "management",
        "manage",
        "conservative",
        "noninvasive",
        "non-invasive",
        "chemotherapy",
        "radiotherapy",
        "immunotherapy",
        "targeted",
        "surgery",
        "resection",
        "neoadjuvant",
        "adjuvant",
        "ablation",
        "palliative",
        "palliation",
        "operation",
        "stent",
        "injection",
        "analgesic",
        "physical",
        "exercise",
        "rehabilitation",
        "drug",
        "regimen",
        "randomized",
        "phase",
        "vaccine",
        "vaccination",
        "vaccinations",
        "immunization",
        "immunizations",
    }
    surgical_markers = {"surgery", "surgical", "replacement", "arthroplasty", "resection"}
    noninvasive_markers = {"noninvasive", "non-invasive", "conservative", "physical", "exercise", "rehabilitation"}

    # Adaptive gating: strict first, then relax if too few results.
    min_desired = max(3, min(int(top_k), 8))

    force_title_terms = bool(must_title)

    def _passes(
        r: sqlite3.Row,
        *,
        require_title_terms: bool,
        require_intervention: bool,
        min_overlap: int,
    ) -> bool:
        title_terms = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", r["title"] or "") if len(t) >= 3}
        if (force_title_terms or require_title_terms) and must_title:
            # Allow common synonym expansions for higher recall without losing intent.
            if "arthritis" in must_title:
                if "knee" in must_title and "knee" not in title_terms:
                    return False
                if "arthritis" not in title_terms and "osteoarthritis" not in title_terms:
                    return False
            elif "cancer" in must_title:
                if "pancreatic" in must_title and "pancreatic" not in title_terms:
                    return False
                if not ({"cancer", "carcinoma", "neoplasm"} & title_terms):
                    return False
            else:
                if not all(_title_has_term(t, title_terms) for t in must_title):
                    return False
        doc_terms = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", f"{r['title']} {r['abstract']}") if len(t) >= 3}
        if wants_noninvasive:
            if any(m in doc_terms for m in surgical_markers) and not any(m in doc_terms for m in noninvasive_markers):
                return False
        if require_intervention and wants_intervention:
            # For treatment queries, enforce intervention intent at the title level where possible.
            # This is important when using hash embeddings (no real semantics) to avoid biomarker/diagnostic papers.
            title_intervention = {
                "treat",
                "treated",
                "treating",
                "treatment",
                "therapy",
                "therapeutic",
                "management",
                "manage",
                "conservative",
                "noninvasive",
                "non-invasive",
                "trial",
                "randomized",
                "phase",
                "surgery",
                "resection",
                "neoadjuvant",
                "adjuvant",
                "chemotherapy",
                "radiotherapy",
                "immunotherapy",
                "targeted",
                "ablation",
                "palliative",
                "palliation",
                "operation",
                "stent",
                "injection",
                "physical",
                "exercise",
                "rehabilitation",
                "drug",
                "regimen",
                "vaccine",
                "vaccination",
                "vaccinations",
                "immunization",
                "immunizations",
            }
            if not any(m in title_terms for m in title_intervention) and not any(
                m in doc_terms for m in intervention_soft_markers
            ):
                return False
            # Also require a core intervention signal somewhere in the paper (or a review/meta-analysis).
            if not any(m in doc_terms for m in intervention_core_markers) and not any(
                m in doc_terms for m in intervention_soft_markers
            ):
                return False
        overlap = len(q_terms & doc_terms)
        vscore = vec_score_map.get(r["pmid"], 0.0) if use_vectors else 0.0
        if overlap < min_overlap and vscore < settings.min_vector_score:
            return False
        return True

    if wants_intervention:
        # Keep intervention focus for treatment/therapy queries; only relax it as a last resort.
        gate_levels = [
            {"require_title_terms": True, "require_intervention": True, "min_overlap": required_overlap},
            {"require_title_terms": True, "require_intervention": True, "min_overlap": max(1, required_overlap - 1)},
        ]
    else:
        gate_levels = [
            {"require_title_terms": True, "require_intervention": False, "min_overlap": required_overlap},
            {"require_title_terms": True, "require_intervention": False, "min_overlap": max(1, required_overlap - 1)},
        ]

    def _append_result(pmid: str, score: float, r: sqlite3.Row) -> None:
        authors = json.loads(r["authors_json"] or "[]")
        mesh_terms = json.loads(r["mesh_terms_json"] or "[]")
        keywords = json.loads(r["keywords_json"] or "[]")
        pub_types = json.loads(r["publication_types_json"] or "[]")
        citation = {
            "pmid": pmid,
            "title": r["title"],
            "journal": r["journal"],
            "year": r["year"],
            "authors": authors,
            "doi": r["doi"],
        }
        evidence = [{"text": s.text, "why": s.why} for s in pick_evidence_snippets(r["abstract"], expanded_query, max_snippets=3)]
        key_points = [e["text"] for e in evidence if isinstance(e, dict) and e.get("text")]
        if not key_points and (r["abstract"] or "").strip():
            key_points = [(r["abstract"] or "").strip()[:240]]
        results.append(
            {
                "pmid": pmid,
                "score": float(score if rerank else base_score_map.get(pmid, score)),
                "title": r["title"],
                "abstract": r["abstract"],
                "citation": citation,
                "mesh_terms": mesh_terms,
                "keywords": keywords,
                "publication_types": pub_types,
                "disease_area": r["disease_area"],
                "trial_stage": r["trial_stage"],
                "evidence": evidence,
                "key_points": key_points[:3],
            }
        )

    seen_pmids: set[str] = set()
    for pmid, score in rescored:
        if pmid not in by_pmid:
            continue
        if filters_active and pmid not in allowed_pmids:
            continue
        if pmid in seen_pmids:
            continue
        r = by_pmid[pmid]

        accepted = False
        for lvl_i, lvl in enumerate(gate_levels):
            if not _passes(r, **lvl):
                continue
            if lvl_i > 0 and len(results) >= min_desired:
                continue
            accepted = True
            break
        if not accepted:
            continue

        _append_result(pmid, score, r)
        seen_pmids.add(pmid)
        if len(results) >= top_k:
            break

    # Backfill pass: if strict gates under-fill results, relax carefully to meet top_k.
    if len(results) < top_k:
        backfill_levels = [
            {"require_title_terms": False, "require_intervention": wants_intervention, "min_overlap": 1},
            {"require_title_terms": False, "require_intervention": False, "min_overlap": 1},
            {"require_title_terms": False, "require_intervention": False, "min_overlap": 0},
        ]
        for lvl in backfill_levels:
            for pmid, score in rescored:
                if len(results) >= top_k:
                    break
                if pmid not in by_pmid:
                    continue
                if filters_active and pmid not in allowed_pmids:
                    continue
                if pmid in seen_pmids:
                    continue
                r = by_pmid[pmid]
                if wants_noninvasive:
                    doc_terms = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", f"{r['title']} {r['abstract']}") if len(t) >= 3}
                    if any(m in doc_terms for m in surgical_markers) and not any(m in doc_terms for m in noninvasive_markers):
                        continue
                if not _passes(r, **lvl):
                    continue
                _append_result(pmid, score, r)
                seen_pmids.add(pmid)
            if len(results) >= top_k:
                break

    results.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return results
