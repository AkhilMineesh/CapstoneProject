from __future__ import annotations

import json
import os

import httpx


class OpenAIReranker:
    def __init__(self, base_url: str, api_key: str, model: str):
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    def provider_name(self) -> str:
        return "openai"

    def model_id(self) -> str:
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        headers = {"Authorization": f"Bearer {self._api_key}"}
        org = (os.getenv("MEDRAG_OPENAI_ORG_ID") or os.getenv("OPENAI_ORG_ID") or "").strip()
        proj = (os.getenv("MEDRAG_OPENAI_PROJECT_ID") or os.getenv("OPENAI_PROJECT_ID") or "").strip()
        if org:
            headers["OpenAI-Organization"] = org
        if proj:
            headers["OpenAI-Project"] = proj
        prompt = {
            "query": query,
            "passages": passages,
            "task": "Return a JSON object: {\"scores\": [0..1 ...]} aligned with passages.",
        }
        with httpx.Client(base_url=self._base_url, headers=headers, timeout=90.0) as client:
            r = client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "You score medical-research passage relevance. Output JSON only."},
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                },
            )
            r.raise_for_status()
            data = r.json()
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        obj = json.loads(content)
        scores = obj.get("scores")
        if not isinstance(scores, list) or len(scores) != len(passages):
            raise RuntimeError("OpenAI reranker returned unexpected JSON; expected {\"scores\": [...]} aligned to passages.")
        out: list[float] = []
        for s in scores:
            try:
                v = float(s)
            except Exception:  # noqa: BLE001
                v = 0.0
            out.append(max(0.0, min(1.0, v)))
        return out
