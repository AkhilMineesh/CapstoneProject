from __future__ import annotations

from ...settings import settings


class LocalSentenceTransformerProvider:
    def __init__(self):
        # Import probe (auto-selection depends on this).
        import sentence_transformers  # noqa: F401

    def provider_name(self) -> str:
        return "local"

    def model_id(self) -> str:
        return settings.embedding_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(settings.embedding_model)
        vectors = model.encode(
            texts,
            batch_size=settings.embedding_batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [list(map(float, v)) for v in vectors]
