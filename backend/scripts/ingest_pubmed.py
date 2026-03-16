from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Generator, Iterable

from array import array

# Allow running as a script from repo root or backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import db_conn, migrate, rebuild_fts, upsert_papers  # noqa: E402
from app.retrieval.embedding import embed_texts  # noqa: E402
from app.retrieval.models.registry import get_embedding_provider  # noqa: E402
from app.settings import settings  # noqa: E402


_PHASE_RE = re.compile(r"\bphase\s*(i{1,3}|iv|1|2|3|4)\b", re.I)


def _trial_stage(publication_types: list[str], title: str, abstract: str) -> str | None:
    for pt in publication_types:
        m = _PHASE_RE.search(pt or "")
        if m:
            return f"phase {m.group(1).lower().replace('1','i').replace('2','ii').replace('3','iii').replace('4','iv')}"
    m = _PHASE_RE.search(f"{title}\n{abstract}")
    if m:
        return f"phase {m.group(1).lower().replace('1','i').replace('2','ii').replace('3','iii').replace('4','iv')}"
    return None


def _disease_area(mesh_terms: list[str]) -> str | None:
    patterns = (
        "neoplasms",
        "cancer",
        "carcinoma",
        "arthritis",
        "diabetes",
        "asthma",
        "stroke",
        "myocardial",
        "covid",
        "influenza",
        "infection",
        "depression",
        "schizophrenia",
        "alzheimer",
        "parkinson",
    )
    for t in mesh_terms:
        tl = (t or "").lower()
        if any(p in tl for p in patterns):
            return t
    return mesh_terms[0] if mesh_terms else None


def parse_pubmed_xml(path: Path, limit: int | None) -> Generator[dict[str, Any], None, None]:
    import xml.etree.ElementTree as ET
    import gzip

    # PubMed baseline XML can be huge; iterparse keeps memory bounded.
    n = 0
    fobj = gzip.open(str(path), "rb") if path.suffix.lower() == ".gz" else open(path, "rb")
    try:
        ctx = ET.iterparse(fobj, events=("end",))
        for _event, elem in ctx:
            if elem.tag != "PubmedArticle":
                continue

            def text_at(p: str) -> str | None:
                node = elem.find(p)
                if node is None:
                    return None
                return "".join(node.itertext()).strip() or None

            pmid = text_at("./MedlineCitation/PMID")
            if not pmid:
                elem.clear()
                continue

            title = text_at("./MedlineCitation/Article/ArticleTitle") or ""
            abstract_nodes = elem.findall("./MedlineCitation/Article/Abstract/AbstractText")
            abstract = " ".join(
                ["".join(x.itertext()).strip() for x in abstract_nodes if "".join(x.itertext()).strip()]
            )
            journal = text_at("./MedlineCitation/Article/Journal/Title")
            year = text_at("./MedlineCitation/Article/Journal/JournalIssue/PubDate/Year")
            if not year:
                medline_date = text_at("./MedlineCitation/Article/Journal/JournalIssue/PubDate/MedlineDate")
                if medline_date:
                    m = re.search(r"\b(19|20)\d{2}\b", medline_date)
                    year = m.group(0) if m else None
            year_i = int(year) if year and year.isdigit() else None

            authors = []
            for a in elem.findall("./MedlineCitation/Article/AuthorList/Author"):
                last = (a.findtext("LastName") or "").strip()
                fore = (a.findtext("ForeName") or "").strip()
                if last and fore:
                    authors.append(f"{fore} {last}")
                elif last:
                    authors.append(last)

            mesh_terms = []
            for mh in elem.findall("./MedlineCitation/MeshHeadingList/MeshHeading/DescriptorName"):
                t = ("".join(mh.itertext()) or "").strip()
                if t:
                    mesh_terms.append(t)

            keywords = []
            for kw in elem.findall("./MedlineCitation/KeywordList/Keyword"):
                t = ("".join(kw.itertext()) or "").strip()
                if t:
                    keywords.append(t)

            publication_types = []
            for pt in elem.findall("./MedlineCitation/Article/PublicationTypeList/PublicationType"):
                t = ("".join(pt.itertext()) or "").strip()
                if t:
                    publication_types.append(t)

            doi = None
            for el in elem.findall(".//ArticleIdList/ArticleId"):
                if (el.attrib or {}).get("IdType") == "doi":
                    doi = ("".join(el.itertext()) or "").strip() or None
                    break
            if not doi:
                for el in elem.findall("./MedlineCitation/Article/ELocationID"):
                    if (el.attrib or {}).get("EIdType") == "doi":
                        doi = ("".join(el.itertext()) or "").strip() or None
                        break

            yield {
                "pmid": str(pmid),
                "title": title,
                "abstract": abstract,
                "year": year_i,
                "journal": journal,
                "authors": authors,
                "mesh_terms": mesh_terms,
                "keywords": keywords,
                "publication_types": publication_types,
                "doi": doi,
                "disease_area": _disease_area(mesh_terms),
                "trial_stage": _trial_stage(publication_types, title, abstract),
            }

            n += 1
            elem.clear()
            if limit is not None and n >= limit:
                break
    finally:
        try:
            fobj.close()
        except Exception:  # noqa: BLE001
            pass


def parse_hf_pubmed(limit: int | None) -> Iterable[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("HuggingFace ingestion requires `datasets` (pip install datasets).") from e

    ds = load_dataset("ncbi/pubmed", split="train")
    n = 0
    for row in ds:
        pmid = str(row.get("pmid") or row.get("PMID") or "")
        if not pmid:
            continue
        title = row.get("title") or row.get("Title") or ""
        abstract = row.get("abstract") or row.get("Abstract") or ""
        journal = row.get("journal") or row.get("Journal") or None
        year = row.get("year") or row.get("publication_year") or None
        year_i = int(year) if isinstance(year, int) or (isinstance(year, str) and year.isdigit()) else None
        authors = row.get("authors") or []
        mesh_terms = row.get("mesh_terms") or row.get("MeSH_terms") or []
        keywords = row.get("keywords") or []
        publication_types = row.get("publication_types") or row.get("PublicationType") or []
        yield {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "year": year_i,
            "journal": journal,
            "authors": authors,
            "mesh_terms": mesh_terms,
            "keywords": keywords,
            "publication_types": publication_types,
            "doi": row.get("doi") or None,
            "disease_area": _disease_area(mesh_terms),
            "trial_stage": _trial_stage(publication_types, title, abstract),
        }
        n += 1
        if limit is not None and n >= limit:
            break


def build_embeddings(conn: sqlite3.Connection, reembed: bool = False, limit: int | None = None) -> int:
    # PubMed baseline ingestion can involve thousands/millions of abstracts.
    # Never send all texts in a single embedding request: payload size will be huge and will time out.
    # Keep batches small; allow overriding via env vars for tuning.
    batch_size = int(os.getenv("MEDRAG_EMBED_BATCH_SIZE", "64"))
    max_chars = int(os.getenv("MEDRAG_EMBED_MAX_CHARS", "8000"))
    sleep_s = float(os.getenv("MEDRAG_EMBED_SLEEP_S", "0"))

    provider = get_embedding_provider()
    model_id = provider.model_id()
    print(
        f"[embeddings] provider={provider.provider_name()} model={model_id} batch={batch_size} max_chars={max_chars} reembed={reembed}",
        file=sys.stderr,
    )

    where = ""
    params: list[Any] = []
    if not reembed:
        where = "WHERE pmid NOT IN (SELECT pmid FROM embeddings)"
    if limit is not None:
        limit_sql = f"LIMIT {int(limit)}"
    else:
        limit_sql = ""
    cur = conn.execute(f"SELECT pmid, title, abstract FROM papers {where} {limit_sql}", params)
    rows = cur.fetchall()
    if not rows:
        return 0

    written = 0
    dim: int | None = None

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [f"{r['title']}\n\n{r['abstract']}"[:max_chars] for r in batch]

        vecs = embed_texts(texts)
        if len(vecs) != len(batch) or not vecs:
            raise RuntimeError("Embedding provider returned unexpected output.")

        if dim is None:
            dim = int(len(vecs[0]))
        for r, v in zip(batch, vecs, strict=True):
            if len(v) != dim:
                continue
            blob = array("f", (float(x) for x in v)).tobytes()
            conn.execute(
                """
                INSERT INTO embeddings(pmid, dim, model, vector)
                VALUES(?,?,?,?)
                ON CONFLICT(pmid) DO UPDATE SET dim=excluded.dim, model=excluded.model, vector=excluded.vector;
                """,
                (r["pmid"], dim, model_id, blob),
            )
            written += 1
        conn.commit()

        if sleep_s > 0:
            time.sleep(sleep_s)

    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(settings.db_path), help="SQLite index DB path")
    ap.add_argument("--source", choices=["xml", "hf"], required=True)
    ap.add_argument("--xml-path", help="Path to PubMed baseline XML file (required for --source xml)")
    ap.add_argument("--limit", type=int, default=2000, help="Max number of records to ingest")
    ap.add_argument("--rebuild-fts", action="store_true", help="Rebuild SQLite FTS index after ingestion")
    ap.add_argument("--build-embeddings", action="store_true", help="Build embeddings after ingestion")
    ap.add_argument("--reembed", action="store_true", help="Recompute embeddings even if present")
    args = ap.parse_args()

    db_path = Path(args.db)
    with db_conn(db_path) as conn:
        migrate(conn)

        if args.source == "xml":
            if not args.xml_path:
                raise SystemExit("--xml-path is required when --source xml")
            src = parse_pubmed_xml(Path(args.xml_path), limit=args.limit)
        else:
            src = parse_hf_pubmed(limit=args.limit)

        batch: list[dict[str, Any]] = []
        total = 0
        for item in src:
            if not item.get("abstract") or not item.get("title"):
                continue
            batch.append(item)
            if len(batch) >= 500:
                total += upsert_papers(conn, batch)
                batch.clear()
                print(f"Ingested {total} papers...", file=sys.stderr)
        if batch:
            total += upsert_papers(conn, batch)

        print(f"Ingestion complete: {total} papers", file=sys.stderr)

        if args.rebuild_fts:
            rebuild_fts(conn)
            print("FTS rebuild complete", file=sys.stderr)

        if args.build_embeddings:
            n = build_embeddings(conn, reembed=args.reembed)
            print(f"Embeddings written: {n}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
