from __future__ import annotations

import random
import math
import time

import httpx


class OpenAIEmbeddingProvider:
    def __init__(self, base_url: str, api_key: str, model: str):
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    def provider_name(self) -> str:
        return "openai"

    def model_id(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        headers = {"Authorization": f"Bearer {self._api_key}"}
        timeout = httpx.Timeout(connect=30.0, read=180.0, write=180.0, pool=30.0)
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

        # Network timeouts are common during large ingestion runs. Retry a few times with backoff.
        # This is especially important for 429/5xx and transient timeouts.
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                with httpx.Client(base_url=self._base_url, headers=headers, timeout=timeout, limits=limits) as client:
                    r = client.post("/embeddings", json={"model": self._model, "input": texts})
                    r.raise_for_status()
                    data = r.json()
                break
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                last_exc = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                retryable = isinstance(e, (httpx.TimeoutException, httpx.NetworkError)) or status in (429, 500, 502, 503, 504)
                if not retryable or attempt >= 4:
                    raise
                # Exponential backoff with jitter.
                sleep_s = min(30.0, (2.0**attempt)) + random.random()
                time.sleep(sleep_s)
        else:  # pragma: no cover
            raise last_exc or RuntimeError("OpenAI embeddings request failed.")

        out: list[list[float]] = []
        for item in data.get("data") or []:
            v = item.get("embedding") or []
            if not isinstance(v, list) or not v:
                out.append([])
                continue
            vec = [float(x) for x in v]
            norm = math.sqrt(sum((x * x for x in vec))) + 1e-12
            out.append([x / norm for x in vec])
        if len(out) != len(texts):
            raise RuntimeError("OpenAI embeddings returned an unexpected number of vectors.")
        return out
