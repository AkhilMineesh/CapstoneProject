from __future__ import annotations

from ...settings import settings


class LocalCrossEncoderReranker:
    def __init__(self):
        import sentence_transformers  # noqa: F401

    def provider_name(self) -> str:
        return "local"

    def model_id(self) -> str:
        return settings.rerank_model

    def score(self, query: str, passages: list[str]) -> list[float]:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(settings.rerank_model)
        pairs = [(query, p) for p in passages]
        scores = model.predict(pairs, show_progress_bar=False)
        return [float(s) for s in scores]
