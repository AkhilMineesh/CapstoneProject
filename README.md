# MedRAG: PubMed Research Chat + Retrieval

Medical research retrieval and abstract-level analysis UI backed by a local PubMed index.

- Chat-style frontend with a left history sidebar and a dedicated results page per query
- PubMed baseline ingestion into a local SQLite database + full-text search (FTS)
- Hybrid retrieval (keyword + vector when available) with relevance gating to omit loosely/unrelated results
- Evidence snippets + PubMed links

This is abstract-level analysis only (PubMed/MEDLINE abstracts). It is not a clinical decision tool.

## Repo Layout
- `backend/`: Flask API + ingestion/indexing (SQLite + FTS + embeddings)
- `frontend/`: React (Vite) chatbot-style UI

## Setup

### 1) Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the API (port 8000):
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.main
```

Health check:
```powershell
curl http://localhost:8000/health
```

### 2) Dataset Ingestion + Indexing (PubMed baseline)

Dataset: PubMed/MEDLINE baseline XML from the official downloads page:
- https://pubmed.ncbi.nlm.nih.gov/download/

#### Step A: Download baseline files (large)
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\download_pubmed_baseline.py --out data\pubmed_baseline --max-files 50
```

#### Step B: Ingest + build indexes
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\ingest_pubmed_dir.py --dir data\pubmed_baseline --rebuild-fts --build-embeddings
```

Notes:
- Default DB path is `backend/data/index.db`.
- Re-running ingestion is incremental (it skips already-embedded PMIDs unless you pass `--reembed`).

### Embeddings Providers
Default is a local-only fallback:
- `MEDRAG_EMBEDDINGS_PROVIDER=hash` (works everywhere, no keys required)

Optional local semantic embeddings (requires wheels; typically Python 3.10-3.12):
- Install local model deps in `backend/requirements-local-models.txt`
- Set `MEDRAG_EMBEDDINGS_PROVIDER=local`

Optional OpenAI embeddings (explicit opt-in):
- Set `MEDRAG_EMBEDDINGS_PROVIDER=openai`
- Set `MEDRAG_OPENAI_API_KEY` (or `OPENAI_API_KEY`)

Environment:
- `backend/.env` is auto-loaded if present (see `backend/.env.example`).

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

### Similar Papers
`GET /api/related/<pmid>`

### Multimodal endpoints (best-effort extraction)
- `POST /api/query/document` (txt/pdf/docx)
- `POST /api/query/image`
- `POST /api/query/audio`

## Frontend Demo
```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to `http://localhost:8000`.

## Example Queries
- `Latest treatments for early-stage pancreatic cancer`
- `Non-invasive therapy for knee arthritis`
- `mRNA vaccine studies published after 2022`

