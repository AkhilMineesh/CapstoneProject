from __future__ import annotations

from .models.registry import get_rerank_provider


def rerank_pairs(query: str, passages: list[str]) -> list[float]:
    provider = get_rerank_provider()
    if provider is None:
        return []
    return provider.score(query, passages)
