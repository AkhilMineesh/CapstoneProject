from __future__ import annotations

from ...settings import settings


class LocalCrossEncoderReranker:
    _model = None
    _model_id = None

    def __init__(self):
        import sentence_transformers  # noqa: F401

    def provider_name(self) -> str:
        return "local"

    def model_id(self) -> str:
        return settings.rerank_model

    def score(self, query: str, passages: list[str]) -> list[float]:
        from sentence_transformers import CrossEncoder

        # Cache model instance across requests to avoid heavy reload cost.
        if self.__class__._model is None or self.__class__._model_id != settings.rerank_model:
            self.__class__._model = CrossEncoder(settings.rerank_model)
            self.__class__._model_id = settings.rerank_model
        model = self.__class__._model
        pairs = [(query, p) for p in passages]
        scores = model.predict(pairs, show_progress_bar=False)
        return [float(s) for s in scores]
