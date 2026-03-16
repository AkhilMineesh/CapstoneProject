from __future__ import annotations

import heapq
import math
import sqlite3
from array import array
from dataclasses import dataclass
from typing import Iterable


@dataclass
class VectorSearchHit:
    pmid: str
    score: float


class VectorIndex:
    def __init__(self):
        self._pmids: list[str] | None = None
        self._vectors: list[array] | None = None
        self._model: str | None = None

    def _load(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("SELECT pmid, dim, model, vector FROM embeddings")
        pmids: list[str] = []
        vecs: list[array] = []
        model_name: str | None = None
        dim: int | None = None
        for row in cur:
            model_name = row["model"]
            dim = int(row["dim"])
            v = array("f")
            v.frombytes(row["vector"])
            if dim is None or len(v) != dim:
                continue
            # Normalize defensively.
            n = math.sqrt(sum((x * x for x in v))) + 1e-12
            v = array("f", (x / n for x in v))
            pmids.append(row["pmid"])
            vecs.append(v)
        if not vecs:
            self._pmids = []
            self._vectors = []
            self._model = model_name
            return
        self._pmids = pmids
        self._vectors = vecs
        self._model = model_name

    def ensure_loaded(self, conn: sqlite3.Connection) -> None:
        if self._vectors is None or self._pmids is None:
            self._load(conn)

    def search(self, conn: sqlite3.Connection, query_vec: list[float], top_k: int) -> list[VectorSearchHit]:
        self.ensure_loaded(conn)
        if self._vectors is None or self._pmids is None or len(self._vectors) == 0:
            return []
        q = array("f", (float(x) for x in query_vec))
        qn = math.sqrt(sum((x * x for x in q))) + 1e-12
        q = array("f", (x / qn for x in q))

        def dot(a: array, b: array) -> float:
            return sum((x * y for x, y in zip(a, b, strict=False)))

        k = max(1, int(top_k))
        scored = [(dot(v, q), i) for i, v in enumerate(self._vectors)]
        top = heapq.nlargest(min(k, len(scored)), scored, key=lambda t: t[0])
        return [VectorSearchHit(pmid=self._pmids[i], score=float(s)) for s, i in top]


_VECTOR_INDEX = VectorIndex()


def vector_search(conn: sqlite3.Connection, query_vec: list[float], top_k: int) -> list[VectorSearchHit]:
    return _VECTOR_INDEX.search(conn, query_vec, top_k=top_k)


def vector_search_subset(
    conn: sqlite3.Connection, query_vec: list[float], pmids: Iterable[str], top_k: int
) -> list[VectorSearchHit]:
    """
    Fast exact vector search over a restricted candidate set.

    This avoids scanning the entire embeddings table (O(N)) which becomes very slow once you ingest
    hundreds of thousands of papers.
    """
    pmid_list = [p for p in pmids if p]
    if not pmid_list:
        return []

    q = array("f", (float(x) for x in query_vec))
    qn = math.sqrt(sum((x * x for x in q))) + 1e-12
    q = array("f", (x / qn for x in q))

    def dot(a: array, b: array) -> float:
        return sum((x * y for x, y in zip(a, b, strict=False)))

    k = max(1, int(top_k))
    heap: list[tuple[float, str]] = []  # min-heap of (score, pmid)

    # SQLite has a parameter limit; chunk the IN list.
    chunk_size = 900
    for i in range(0, len(pmid_list), chunk_size):
        chunk = pmid_list[i : i + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        cur = conn.execute(
            f"SELECT pmid, dim, vector FROM embeddings WHERE pmid IN ({placeholders})",
            chunk,
        )
        for row in cur:
            v = array("f")
            v.frombytes(row["vector"])
            dim = int(row["dim"])
            if len(v) != dim or dim <= 0:
                continue
            # Normalize defensively in case older vectors weren't normalized at write-time.
            vn = math.sqrt(sum((x * x for x in v))) + 1e-12
            v = array("f", (x / vn for x in v))
            s = float(dot(v, q))
            if len(heap) < k:
                heapq.heappush(heap, (s, row["pmid"]))
            else:
                if s > heap[0][0]:
                    heapq.heapreplace(heap, (s, row["pmid"]))

    heap.sort(key=lambda t: t[0], reverse=True)
    return [VectorSearchHit(pmid=pmid, score=float(score)) for score, pmid in heap]
