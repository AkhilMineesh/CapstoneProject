# MedAssist: PubMed Research Chat + Retrieval

Medical research retrieval and abstract-level analysis UI backed by a local PubMed index.

- Chat-style frontend with history sidebar + results view
- PubMed baseline ingestion into local SQLite + FTS
- Hybrid retrieval (keyword + vector embeddings)
- Evidence snippets, citation metadata, and cross-paper synthesis
- Multimodal query intake (text/document/image/audio)

This is abstract-level research support only. It is **not** a clinical decision tool.

## Repo Layout
- `backend/`: Flask API, ingestion, indexing, retrieval
- `frontend/`: React + Vite UI

## 1) Backend Setup (Windows)
From project root:

```powershell
cd backend
python -m venv testenv
.\testenv\Scripts\activate
pip install -r requirements.txt
```

Create env file:

```powershell
Copy-Item .env.example .env
```

Then edit `backend\.env` and set at minimum:
- `MEDRAG_OPENAI_API_KEY=<your_key>`
- `MEDRAG_EMBEDDINGS_PROVIDER=openai`
- `MEDRAG_OPENAI_EMBEDDING_MODEL=text-embedding-3-small`

Optional but recommended for deeper insights:
- `MEDRAG_OPENAI_CLINICAL_REASONING=true`
- `MEDRAG_OPENAI_REASONING_MODEL=gpt-4.1-mini`

Important:
- `backend/.env` is auto-loaded by the app.
- If logs show `provider=hash`, your OpenAI env config was not loaded correctly.

## 2) Download Latest PubMed Baseline Files
Use the latest N files (recommended starting size: 15):

```powershell
cd backend
.\testenv\Scripts\python scripts\download_pubmed_baseline.py --out data\pubmed_baseline --max-files 15 --latest
```

## 3) Ingest + Build Embeddings

```powershell
cd backend
.\testenv\Scripts\python scripts\ingest_pubmed_dir.py --dir data\pubmed_baseline --build-embeddings --latest --max-files 15
```

Notes:
- Ingestion is incremental.
- FTS is auto-rebuilt if missing.
- Embeddings can take significant time (especially with OpenAI + large paper counts).
- Do **not** Ctrl+C while embeddings are still being written if you want a complete embedding pass.

## 4) Run Backend API

```powershell
cd backend
.\testenv\Scripts\python -m app.main
```

Health check:

```powershell
curl http://localhost:8000/health
```

## 5) Run Frontend
In a new terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open:
- `http://localhost:5173`

## Core API Endpoints
- `POST /api/analyze` - main text query retrieval
- `POST /api/query/document` - document upload query
- `POST /api/query/image` - image upload query
- `POST /api/query/audio` - audio upload/transcription query
- `GET /api/metadata/options` - filters metadata
- `GET /api/paper/<pmid>` - paper details
- `GET /api/related/<pmid>` - related papers
- `GET /api/capabilities` - endpoint discovery

## Example Analyze Request

```json
{
  "query": "Latest treatments for early-stage pancreatic cancer",
  "filters": { "publication_year_from": 2022 },
  "rerank": true,
  "include_insights": true
}
```

## Example Casual Query Support
Casual prompts are normalized before retrieval, for example:
- `I need you to retrieve articles on cancer` -> normalized for stronger retrieval

## Troubleshooting
- `Cannot find native binding` (frontend/Vite rolldown):
  - Delete `frontend\node_modules` and `frontend\package-lock.json`, then run `npm.cmd install` again.
- `httpx.RemoteProtocolError` while downloading PubMed:
  - Re-run the same download command; downloader has retries for transient disconnects.
- Very slow search:
  - Ensure embeddings are built with OpenAI provider and ingestion completed successfully.

## Safety / Scope
- Results and synthesis are based on PubMed abstracts and metadata.
- Verify with full text, trial design, endpoints, and inclusion/exclusion criteria before real-world decisions.
