from __future__ import annotations

from .models.registry import get_embedding_provider


def embed_texts(texts: list[str]) -> list[list[float]]:
    provider = get_embedding_provider()
    return provider.embed(texts)
