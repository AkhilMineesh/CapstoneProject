from __future__ import annotations

import hashlib
import math
import re


class HashEmbeddingProvider:
    def __init__(self, dim: int = 384):
        self._dim = int(dim)
        self._tok_re = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")

    def provider_name(self) -> str:
        return "hash"

    def model_id(self) -> str:
        return f"hash-embedding-v1-{self._dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        v = [0.0] * self._dim
        toks = [t.lower() for t in self._tok_re.findall(text or "")]
        if not toks:
            return v
        for t in toks:
            h = hashlib.blake2b(t.encode("utf-8"), digest_size=8).digest()
            n = int.from_bytes(h, "little", signed=False)
            idx = n % self._dim
            sign = -1.0 if (n >> 63) & 1 else 1.0
            v[idx] += sign
        norm = math.sqrt(sum((x * x for x in v))) + 1e-12
        return [x / norm for x in v]
