# MedRAG: Multimodal Medical Research Retrieval + Analysis

AI-powered medical research retrieval and analysis system for clinicians/researchers:
- Multimodal query input: text, document upload, image OCR, audio (voice) transcription
- Hybrid research retrieval: semantic vector search + keyword FTS search
- Cross-encoder re-ranking for improved relevance
- Metadata filtering: publication year, journal, study type, disease area, clinical trial stage
- Medical terminology guardrails + MeSH-based query expansion
- Evidence-based results: PMID citations + evidence snippets
- Research intelligence: multi-paper summarization, conflicting signals, trends, and a lightweight knowledge graph
- Multi-agent analysis: Retrieval, Methodology Critic, Statistical Reviewer, Clinical Applicability, Summarizer

This is abstract-level analysis only (PubMed/MEDLINE abstracts). It is not a clinical decision tool.

## Repo Layout
- `backend/`: FastAPI service + ingestion/indexing
- `frontend/`: React (Vite) demo UI

## Setup

### 1) Backend
From the repo root:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the API (Flask dev server):
```powershell
cd backend
$env:FLASK_APP = "app.main:app"
python -m flask run --port 8000
```

Health check:
```powershell
curl http://localhost:8000/health
```

### 2) Dataset Ingestion + Indexing

Dataset: PubMed/MEDLINE research abstracts
- Download: https://pubmed.ncbi.nlm.nih.gov/download/
- Alternate: https://huggingface.co/datasets/ncbi/pubmed
- Alternate: https://www.kaggle.com/datasets/bonhart/pubmed-abstracts
- Text mining: https://pmc.ncbi.nlm.nih.gov/tools/textmining/
- NCBI BioNLP: https://www.ncbi.nlm.nih.gov/research/bionlp/Data

#### Option A: Ingest PubMed baseline XML (recommended)
1. Download a baseline XML file (example: `pubmed24n0001.xml.gz`) and unzip it.
2. Run ingestion, build keyword index (FTS), and build embeddings:
```powershell
cd backend
python scripts\ingest_pubmed.py --source xml --xml-path C:\path\to\pubmed24n0001.xml --limit 2000 --rebuild-fts --build-embeddings
```

#### Option B: Ingest HuggingFace dataset (demo convenience)
```powershell
cd backend
pip install datasets
python scripts\ingest_pubmed.py --source hf --limit 2000 --rebuild-fts --build-embeddings
```

Notes:
- The SQLite index lives at `backend/data/index.db`.
- Embeddings are stored in SQLite in `embeddings.vector` as float32 blobs.
- For large-scale ingestion, increase `--limit` gradually and consider adding FAISS (see optional deps in `backend/requirements.txt`).

### Embeddings / Re-ranking Providers
This project supports:
- Pure-Python hashed embeddings (default fallback): runs everywhere, no keys required
- Local models (optional): `sentence-transformers` + `torch` + `numpy` (generally needs Python 3.10-3.12 wheels)
- Remote embeddings (works on Python 3.14): set `MEDRAG_OPENAI_API_KEY` to use OpenAI embeddings via `httpx`

Example (PowerShell) to use OpenAI embeddings:
```powershell
cd backend
$env:MEDRAG_OPENAI_API_KEY = "<your key>"
$env:MEDRAG_EMBEDDINGS_PROVIDER = "openai"
python scripts\ingest_pubmed.py --source xml --xml-path C:\path\to\pubmed.xml --limit 2000 --rebuild-fts --build-embeddings
```

Optional OpenAI reranking (LLM-based) can be enabled by setting:
- `MEDRAG_OPENAI_RERANK_MODEL` (a chat-capable model name)

## API Usage

### Analyze (hybrid retrieval + agents + intelligence)
`POST /api/analyze`
```json
{
  "query": "mRNA vaccine studies published after 2022",
  "filters": { "publication_year_from": 2023 },
  "top_k": 20,
  "rerank": true,
  "include_insights": true
}
```

Response includes:
- `results[]`: ranked papers with `citation` (PMID, title, journal, year, authors), evidence snippets, and metadata
- `insights`: abstract-level summary, conflicts, trends, knowledge graph, guardrails, expanded query
- `agent_reports[]`: notes from each specialized agent

### Multimodal endpoints
- `POST /api/query/document` (txt/pdf/docx)
- `POST /api/query/image` (OCR via tesseract)
- `POST /api/query/audio` (ASR via faster-whisper)

These endpoints extract text and then run the same analysis pipeline.

## Frontend Demo
```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to `http://localhost:8000`.

## Quick Smoke Test (No Downloads)
This seeds a tiny demo index (not real PubMed records) so you can verify end-to-end wiring quickly:
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\seed_demo.py
```

## Example Queries
- `Latest treatments for early-stage pancreatic cancer`
- `Non-invasive therapy for knee arthritis`
- `mRNA vaccine studies published after 2022`

## Example Output (What To Expect)
- Results list with PubMed links (`https://pubmed.ncbi.nlm.nih.gov/<PMID>/`)
- Evidence snippets taken from abstract sentences that overlap the expanded query terms
- Insights panel:
  - Multi-paper summary (extractive, abstract-level)
  - Conflicting signals detection (heuristic stance on outcomes)
  - Trend counts for common MeSH/keyword terms by year
  - Knowledge graph preview connecting disease area, treatments, and outcomes

## Optional Multimodal Dependencies
Multimodal endpoints require extra packages and system tools:
- PDF: `pypdf`
- DOCX: `python-docx`
- Image OCR: `pillow`, `pytesseract`, and the `tesseract` binary installed and on PATH
- Audio: `faster-whisper` and audio deps (`soundfile`)

See `backend/requirements.txt` for optional dependency pins.
