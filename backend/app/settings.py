from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(repo_root: Path) -> None:
    # Optional dependency; when present, auto-load backend/.env for local dev.
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:  # noqa: BLE001
        return
    # Prefer backend/.env, but also accept repo_root/.env for convenience.
    # Use override=True for backend/.env so it wins over stale PowerShell session env vars
    # (common cause of accidentally selecting OpenAI embeddings and getting 401s).
    load_dotenv(dotenv_path=str((repo_root / "backend" / ".env").resolve()), override=True)
    load_dotenv(dotenv_path=str((repo_root / ".env").resolve()), override=False)


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    return v if v != "" else default


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    v = _env(name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    v = _env(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    v = _env(name)
    if v is None:
        return default
    parts = [p.strip() for p in v.split(",") if p.strip()]
    return parts or default


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    db_path: Path

    embeddings_provider: str
    embedding_model: str
    embedding_batch_size: int

    openai_api_key: str | None
    openai_base_url: str
    openai_embedding_model: str
    openai_reasoning_model: str
    openai_reasoning_timeout_s: float
    openai_clinical_reasoning: bool

    rerank_model: str
    openai_rerank_model: str | None
    rerank_top_k: int

    keyword_top_k: int
    vector_top_k: int
    final_top_k: int
    rrf_k: int
    weight_keyword: float
    weight_vector: float
    min_vector_score: float
    min_query_term_overlap: int

    mesh_expand: bool
    mesh_max_terms: int
    mesh_cache_path: Path

    cors_allow_origins: list[str]


def load_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv(repo_root)
    db_path = Path(_env("MEDRAG_DB_PATH", str(repo_root / "backend" / "data" / "index.db"))).resolve()

    # Default to a safe local-only provider so the system works out of the box.
    # Set MEDRAG_EMBEDDINGS_PROVIDER=openai to enable OpenAI embeddings explicitly.
    embeddings_provider = (_env("MEDRAG_EMBEDDINGS_PROVIDER", "hash") or "hash").lower()
    embedding_model = _env("MEDRAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2") or ""
    embedding_batch_size = _env_int("MEDRAG_EMBEDDING_BATCH_SIZE", 32)

    # Accept either project-prefixed env var or the common OPENAI_API_KEY alias.
    openai_api_key = _env("MEDRAG_OPENAI_API_KEY") or _env("OPENAI_API_KEY")
    openai_base_url = _env("MEDRAG_OPENAI_BASE_URL", "https://api.openai.com/v1") or ""
    openai_embedding_model = _env("MEDRAG_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small") or ""
    openai_reasoning_model = _env("MEDRAG_OPENAI_REASONING_MODEL", "gpt-4.1-mini") or ""
    openai_reasoning_timeout_s = _env_float("MEDRAG_OPENAI_REASONING_TIMEOUT_S", 120.0)
    openai_clinical_reasoning = _env_bool("MEDRAG_OPENAI_CLINICAL_REASONING", True)

    rerank_model = _env("MEDRAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2") or ""
    openai_rerank_model = _env("MEDRAG_OPENAI_RERANK_MODEL")
    rerank_top_k = _env_int("MEDRAG_RERANK_TOP_K", 30)

    keyword_top_k = _env_int("MEDRAG_KEYWORD_TOP_K", 100)
    vector_top_k = _env_int("MEDRAG_VECTOR_TOP_K", 100)
    final_top_k = _env_int("MEDRAG_FINAL_TOP_K", 10)
    rrf_k = _env_int("MEDRAG_RRF_K", 60)
    weight_keyword = _env_float("MEDRAG_WEIGHT_KEYWORD", 0.45)
    weight_vector = _env_float("MEDRAG_WEIGHT_VECTOR", 0.55)
    min_vector_score = _env_float("MEDRAG_MIN_VECTOR_SCORE", 0.18)
    min_query_term_overlap = _env_int("MEDRAG_MIN_QUERY_TERM_OVERLAP", 2)

    # MeSH expansion requires network calls to NCBI eutils; default off for latency and precision.
    mesh_expand = _env_bool("MEDRAG_MESH_EXPAND", False)
    mesh_max_terms = _env_int("MEDRAG_MESH_MAX_TERMS", 5)
    mesh_cache_path = Path(
        _env("MEDRAG_MESH_CACHE_PATH", str(repo_root / "backend" / "data" / "mesh_cache.json")) or ""
    ).resolve()

    cors_allow_origins = _env_list("MEDRAG_CORS_ALLOW_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"])

    return Settings(
        repo_root=repo_root,
        db_path=db_path,
        embeddings_provider=embeddings_provider,
        embedding_model=embedding_model,
        embedding_batch_size=embedding_batch_size,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
        openai_embedding_model=openai_embedding_model,
        openai_reasoning_model=openai_reasoning_model,
        openai_reasoning_timeout_s=openai_reasoning_timeout_s,
        openai_clinical_reasoning=openai_clinical_reasoning,
        rerank_model=rerank_model,
        openai_rerank_model=openai_rerank_model,
        rerank_top_k=rerank_top_k,
        keyword_top_k=keyword_top_k,
        vector_top_k=vector_top_k,
        final_top_k=final_top_k,
        rrf_k=rrf_k,
        weight_keyword=weight_keyword,
        weight_vector=weight_vector,
        min_vector_score=min_vector_score,
        min_query_term_overlap=min_query_term_overlap,
        mesh_expand=mesh_expand,
        mesh_max_terms=mesh_max_terms,
        mesh_cache_path=mesh_cache_path,
        cors_allow_origins=cors_allow_origins,
    )


settings = load_settings()
