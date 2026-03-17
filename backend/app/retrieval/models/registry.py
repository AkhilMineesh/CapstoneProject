from __future__ import annotations

from functools import lru_cache

from ...settings import settings
from .embeddings_hash import HashEmbeddingProvider
from .embeddings_openai import OpenAIEmbeddingProvider
from .embeddings_sentence_transformers import LocalSentenceTransformerProvider
from .rerank_openai import OpenAIReranker
from .rerank_sentence_transformers import LocalCrossEncoderReranker


@lru_cache(maxsize=1)
def get_embedding_provider():
    pref = (settings.embeddings_provider or "auto").lower()

    # Safety: never call OpenAI implicitly. Only use OpenAI when explicitly selected.
    # This prevents accidental 401s (or unexpected spend) when users have OPENAI_API_KEY set globally.
    if pref == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "MEDRAG_EMBEDDINGS_PROVIDER=openai requires MEDRAG_OPENAI_API_KEY (or OPENAI_API_KEY)."
            )
        return OpenAIEmbeddingProvider(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
        )

    if pref in ("local", "auto"):
        try:
            return LocalSentenceTransformerProvider()
        except Exception as e:  # noqa: BLE001
            if pref == "local":
                raise
            return HashEmbeddingProvider()

    if pref == "hash":
        return HashEmbeddingProvider()

    raise RuntimeError(f"Unsupported embeddings_provider={settings.embeddings_provider!r}")


def get_embedding_model_id() -> str:
    return get_embedding_provider().model_id()


def get_rerank_provider():
    try:
        return LocalCrossEncoderReranker()
    except Exception:  # noqa: BLE001
        pass
    if settings.openai_api_key and settings.openai_rerank_model:
        return OpenAIReranker(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.openai_rerank_model,
        )
    return None
