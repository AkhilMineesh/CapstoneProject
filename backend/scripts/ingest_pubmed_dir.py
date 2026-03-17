from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import db_conn, migrate, rebuild_fts, upsert_papers  # noqa: E402
from ingest_pubmed import build_embeddings, parse_pubmed_xml  # noqa: E402
from app.settings import settings  # noqa: E402


def _fts_row_count(conn) -> int:
    try:
        return int(conn.execute("SELECT COUNT(1) FROM paper_fts").fetchone()[0])
    except Exception:  # noqa: BLE001
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Directory containing PubMed baseline .xml.gz files")
    ap.add_argument("--db", default=str(settings.db_path), help="SQLite index DB path")
    ap.add_argument("--max-files", type=int, default=0, help="If >0, only ingest first N files (for testing)")
    ap.add_argument(
        "--latest",
        action="store_true",
        help="When used with --max-files, ingest the most recent N files instead of the first N.",
    )
    ap.add_argument("--limit-per-file", type=int, default=0, help="If >0, limit records per file (for testing)")
    ap.add_argument("--rebuild-fts", action="store_true", help="Rebuild FTS after ingestion completes")
    ap.add_argument("--build-embeddings", action="store_true", help="Build embeddings after ingestion completes")
    ap.add_argument("--reembed", action="store_true", help="Recompute embeddings even if present")
    args = ap.parse_args()

    src_dir = Path(args.dir)
    if not src_dir.exists():
        raise SystemExit(f"Directory not found: {src_dir}")

    files = sorted([p for p in src_dir.glob("pubmed*.xml.gz")])
    if not files:
        raise SystemExit("No pubmed*.xml.gz files found in the directory.")
    if args.max_files and args.max_files > 0:
        files = files[-args.max_files :] if args.latest else files[: args.max_files]

    db_path = Path(args.db)
    with db_conn(db_path) as conn:
        migrate(conn)
        total = 0
        for i, fp in enumerate(files, start=1):
            print(f"[{i}/{len(files)}] ingest {fp.name}", file=sys.stderr)
            limit = args.limit_per_file if args.limit_per_file and args.limit_per_file > 0 else None
            gen = parse_pubmed_xml(fp, limit=limit)
            batch: list[dict[str, Any]] = []
            for item in gen:
                if not item.get("abstract") or not item.get("title"):
                    continue
                batch.append(item)
                if len(batch) >= 500:
                    total += upsert_papers(conn, batch)
                    batch.clear()
            if batch:
                total += upsert_papers(conn, batch)
            print(f"total papers={total}", file=sys.stderr)

        # Hybrid retrieval depends on FTS. If the user didn't request rebuild explicitly but
        # the FTS table is empty (common when ingestion is run without --rebuild-fts),
        # rebuild automatically so search returns results.
        if args.rebuild_fts or _fts_row_count(conn) == 0:
            rebuild_fts(conn)
            print("FTS rebuild complete", file=sys.stderr)

        if args.build_embeddings:
            n = build_embeddings(conn, reembed=args.reembed)
            print(f"Embeddings written: {n}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

