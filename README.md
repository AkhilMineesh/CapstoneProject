# MedRAG: PubMed Research Chat + Retrieval

Medical research retrieval and abstract-level analysis UI backed by a local PubMed index.

- Chat-style frontend with a left history sidebar and a dedicated results page per query
- PubMed baseline ingestion into a local SQLite database + full-text search (FTS)
- Semantic reranking that considers the whole query (lightweight local embeddings stored at ingest time)
- Relevance filtering to omit loosely/unrelated results
- Evidence snippets + PubMed links

This is abstract-level analysis only (PubMed/MEDLINE abstracts). It is not a clinical decision tool.

## Repo Layout
- `backend/`: FastAPI service + ingestion/indexing (SQLite + FTS + local semantic rerank)
- `frontend/`: React (Vite) chatbot-style UI

## What Changed
- Backend now requires ingestion of PubMed baseline XML into `backend/data/index.db` (no more demo `papers.json` seed).
- Retrieval was tightened:
  - candidate retrieval uses stronger anchors (phrases/entity tokens) instead of matching any single word
  - candidates are semantically reranked against the full query
  - low-relevance results are omitted
- Frontend was redesigned:
  - left history bar (new chat, select chat, delete chat, clear chats)
  - per-query results page (`/chat/:id/results`) with clickable cards and a pop-up article overview
- `Top K` was removed from the UI; the backend caps results and only returns the most relevant ones.
- Pydantic models were split into one-class-per-file under `backend/app/models/`.
- Optional OpenAI embeddings support was added for higher-quality semantic reranking.

## Setup

### 1) Backend
From the repo root:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the API (FastAPI via Uvicorn):
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Health check:
```powershell
curl http://localhost:8000/health
```

### 2) Dataset Ingestion + Indexing (PubMed baseline)

Dataset: PubMed/MEDLINE baseline XML from the official downloads page:
- https://pubmed.ncbi.nlm.nih.gov/download/

This backend ingests baseline `*.xml.gz` into a vector database (Qdrant) and stores:
- vectors (embeddings) for semantic retrieval
- payload metadata (title, abstract, journal, year, etc.)

#### Start Qdrant (vector database)
Run Qdrant locally (Docker example):
```powershell
docker run --rm -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

By default the backend connects to `http://localhost:6333` (override with `MEDRAG_QDRANT_URL`).

#### Option A: Download baseline files with the script
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\ingest_pubmed_baseline.py --download --rebuild
```

Tip: to ingest more recent records faster, use the latest baseline files:
```powershell
python scripts\ingest_pubmed_baseline.py --download --latest --max-files 50 --rebuild
```

#### Option B: Manually download baseline files, then ingest
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\ingest_pubmed_baseline.py --baseline-dir C:\path\to\baseline --rebuild
```

Notes:
- Default DB path is `backend/data/index.db` (override with `--db-path` or `MEDRAG_DB_PATH`).
- Baseline ingestion is large and can take a long time; ensure you have enough disk space.
- If you change ingestion/reranking code, re-run ingestion with `--rebuild` to refresh stored embeddings.

### Optional: Use OpenAI embeddings (better semantic search)
By default, embeddings are computed locally (no network / no key).

To use OpenAI embeddings during ingestion + query-time reranking:
```powershell
cd backend
$env:MEDRAG_EMBEDDINGS_PROVIDER = "openai"
$env:MEDRAG_OPENAI_API_KEY = "<your key>"
python scripts\ingest_pubmed_baseline.py --download --latest --max-files 50 --rebuild
```

Config:
- `MEDRAG_EMBEDDINGS_PROVIDER`: `local` (default) or `openai`
- `MEDRAG_OPENAI_API_KEY` (or `OPENAI_API_KEY`)
- `MEDRAG_OPENAI_EMBED_MODEL` (default: `text-embedding-3-small`)
- `MEDRAG_OPENAI_EMBED_DIMENSIONS` (optional; reduces vector size)
- `MEDRAG_OPENAI_BASE_URL` (optional; default: `https://api.openai.com/v1`)

## API Usage

### Analyze
`POST /api/analyze`
```json
{
  "query": "Latest treatments for early-stage pancreatic cancer",
  "filters": { "publication_year_from": 2022 },
  "rerank": true,
  "include_insights": true
}
```

Notes:
- `rerank: true` enables semantic reranking (recommended).
- `top_k` is accepted for compatibility, but results are capped and low-relevance items are omitted.

### Multimodal endpoints
- `POST /api/query/document` (txt/pdf/docx) – best-effort text extraction
- `POST /api/query/image` – placeholder text extraction unless you add OCR
- `POST /api/query/audio` – placeholder text extraction unless you add ASR

## Frontend Demo
```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

If `npm` fails in PowerShell due to execution policy, use `npm.cmd` as above.

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to `http://localhost:8000`.

## Example Queries
- `Latest treatments for early-stage pancreatic cancer`
- `Non-invasive therapy for knee arthritis`
- `mRNA vaccine studies published after 2022`
