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

Create your environment file and update values:
```powershell
Copy-Item .env.example .env
```

Then edit `backend\.env` and set the values you need, especially:
- `MEDRAG_EMBEDDINGS_PROVIDER` (`hash`, `local`, or `openai`)
- `MEDRAG_OPENAI_API_KEY` (or `OPENAI_API_KEY`) if using OpenAI
- `MEDRAG_OPENAI_EMBEDDING_MODEL` (optional model override)
- `MEDRAG_OPENAI_CLINICAL_REASONING=true` (optional, for deeper synthesis)

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
python scripts\download_pubmed_baseline.py --out data\pubmed_baseline --max-files 50 --latest
```

#### Step B: Ingest + build indexes
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\ingest_pubmed_dir.py --dir data\pubmed_baseline --build-embeddings --latest --max-files 25
```
It is suggested that you select the number of files you desire to ingest into the database.


Notes:
- Default DB path is `backend/data/index.db`.
- Re-running ingestion is incremental.
- Embeddings are now model-aware: when you switch provider/model (for example from `hash` to `openai`), `--build-embeddings` will refresh rows that were embedded with a different model.

### Embeddings Providers
Default is a local-only fallback:
- `MEDRAG_EMBEDDINGS_PROVIDER=hash` (works everywhere, no keys required)

Optional local semantic embeddings (requires wheels; typically Python 3.10-3.12):
- Install local model deps in `backend/requirements-local-models.txt`
- Set `MEDRAG_EMBEDDINGS_PROVIDER=local`

Optional OpenAI embeddings (explicit opt-in):
- Set `MEDRAG_EMBEDDINGS_PROVIDER=openai`
- Set `MEDRAG_OPENAI_API_KEY` (or `OPENAI_API_KEY`)
- Optional model override: `MEDRAG_OPENAI_EMBEDDING_MODEL=text-embedding-3-small`
- Optional deep clinical reasoning (for richer insight synthesis):
  - `MEDRAG_OPENAI_CLINICAL_REASONING=true`
  - `MEDRAG_OPENAI_REASONING_MODEL=gpt-4.1-mini`
  - `MEDRAG_OPENAI_REASONING_TIMEOUT_S=120`
- After enabling OpenAI, refresh embeddings for your existing papers:
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\ingest_pubmed_dir.py --dir data\pubmed_baseline --build-embeddings
```

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
- `GET /api/capabilities` (API discoverability for external apps)

Multimodal extraction behavior:
- Local-first: uses installed local parsers/OCR/STT when available.
- OpenAI fallback: if local tools are missing, the backend can use OpenAI multimodal models when `MEDRAG_OPENAI_API_KEY` is configured.
- Optional model env vars:
  - `MEDRAG_OPENAI_MULTIMODAL_MODEL` (default `gpt-4.1-mini`) for document/image text extraction
  - `MEDRAG_OPENAI_AUDIO_MODEL` (default `gpt-4o-mini-transcribe`) for audio transcription

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

## Example Research Query + Retrieved Results

### Example Request
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"mRNA vaccine studies published after 2022\",\"filters\":{\"publication_year_from\":2023},\"rerank\":true,\"include_insights\":true}"
```

### Example Retrieved Results (trimmed)
```json
{
  "query": "mRNA vaccine studies published after 2022",
  "results": [
    {
      "pmid": "41439194",
      "title": "Messenger RNA vaccines in the prevention of allergic diseases",
      "score": 0.92,
      "citation": {
        "journal": "Allergy",
        "year": 2025,
        "doi": "10.xxxx/xxxx"
      },
      "evidence": [
        { "text": "Recent mRNA vaccine platforms have expanded beyond infectious disease into allergy prevention.", "why": "query overlap + semantic relevance" }
      ]
    },
    {
      "pmid": "41597174",
      "title": "Advances in mRNA-Based Melanoma Vaccines",
      "score": 0.88,
      "citation": {
        "journal": "Cancers",
        "year": 2026
      }
    }
  ]
}
```

## Example Generated Research Insight / Literature Summary

When `include_insights=true`, the API returns cross-paper synthesis under `insights`.

```json
{
  "insights": {
    "summary": "Recent studies suggest mRNA platforms are expanding into oncology and immune modulation with generally favorable early safety profiles, though trial heterogeneity and short follow-up limit certainty.",
    "key_findings": [
      "Messenger RNA vaccines in the prevention of allergic diseases (2025, PMID 41439194): mRNA platforms show preventive immunologic potential beyond infectious diseases.",
      "Advances in mRNA-Based Melanoma Vaccines (2026, PMID 41597174): Personalized neoantigen strategies show promising anti-tumor immune activation."
    ],
    "guardrails": [
      "Abstract-level synthesis only; verify full-text endpoints and inclusion criteria."
    ]
  }
}
```

In the frontend results page:
- **Result count** appears prominently at the top
- **Evidence Summary** is toggleable
- **Summary content** appears first
- **References** are listed at the end of the summary block

