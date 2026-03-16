from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def db_conn(db_path: Path):
    conn = _connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS papers (
          pmid TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          abstract TEXT NOT NULL,
          year INTEGER,
          journal TEXT,
          authors_json TEXT,
          mesh_terms_json TEXT,
          keywords_json TEXT,
          publication_types_json TEXT,
          doi TEXT,
          disease_area TEXT,
          trial_stage TEXT
        );

        CREATE TABLE IF NOT EXISTS embeddings (
          pmid TEXT PRIMARY KEY,
          dim INTEGER NOT NULL,
          model TEXT NOT NULL,
          vector BLOB NOT NULL,
          FOREIGN KEY(pmid) REFERENCES papers(pmid) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS paper_fts USING fts5(
          pmid UNINDEXED,
          title,
          abstract,
          journal,
          mesh_terms,
          keywords,
          authors,
          publication_types,
          tokenize='porter'
        );

        CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
        CREATE INDEX IF NOT EXISTS idx_papers_journal ON papers(journal);
        CREATE INDEX IF NOT EXISTS idx_papers_disease_area ON papers(disease_area);
        CREATE INDEX IF NOT EXISTS idx_papers_trial_stage ON papers(trial_stage);
        """
    )
    conn.commit()


def upsert_papers(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for r in rows:
        conn.execute(
            """
            INSERT INTO papers(
              pmid,title,abstract,year,journal,authors_json,mesh_terms_json,keywords_json,
              publication_types_json,doi,disease_area,trial_stage
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(pmid) DO UPDATE SET
              title=excluded.title,
              abstract=excluded.abstract,
              year=excluded.year,
              journal=excluded.journal,
              authors_json=excluded.authors_json,
              mesh_terms_json=excluded.mesh_terms_json,
              keywords_json=excluded.keywords_json,
              publication_types_json=excluded.publication_types_json,
              doi=excluded.doi,
              disease_area=excluded.disease_area,
              trial_stage=excluded.trial_stage;
            """,
            (
                r["pmid"],
                r.get("title") or "",
                r.get("abstract") or "",
                r.get("year"),
                r.get("journal"),
                json.dumps(r.get("authors") or []),
                json.dumps(r.get("mesh_terms") or []),
                json.dumps(r.get("keywords") or []),
                json.dumps(r.get("publication_types") or []),
                r.get("doi"),
                r.get("disease_area"),
                r.get("trial_stage"),
            ),
        )
        count += 1
    conn.commit()
    return count


def rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM paper_fts;")
    cur = conn.execute(
        """
        SELECT pmid,title,abstract,journal,authors_json,mesh_terms_json,keywords_json,publication_types_json
        FROM papers
        """
    )
    for row in cur:
        authors = ", ".join(json.loads(row["authors_json"] or "[]"))
        mesh_terms = " ".join(json.loads(row["mesh_terms_json"] or "[]"))
        keywords = " ".join(json.loads(row["keywords_json"] or "[]"))
        pub_types = " ".join(json.loads(row["publication_types_json"] or "[]"))
        conn.execute(
            """
            INSERT INTO paper_fts(pmid,title,abstract,journal,mesh_terms,keywords,authors,publication_types)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                row["pmid"],
                row["title"],
                row["abstract"],
                row["journal"] or "",
                mesh_terms,
                keywords,
                authors,
                pub_types,
            ),
        )
    conn.commit()
