from __future__ import annotations

import json
import os
import re

from flask import Flask, jsonify, request
from flask_cors import CORS

from .agents.orchestrator import run_multi_agent_analysis
from .db import db_conn, migrate
from .multimodal.extract import extract_text_from_audio, extract_text_from_document, infer_query_from_image
from .multimodal.query_compact import compact_query_from_text, simple_query_from_text
from .settings import settings




_IMAGE_QUERY_GENERIC_TERMS = {
    "effect",
    "effects",
    "pathology",
    "pathological",
    "finding",
    "findings",
    "image",
    "figure",
    "chart",
    "screenshot",
    "analysis",
}


def _image_query_fallbacks(query: str) -> list[str]:
    raw = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", query or "") if len(t) >= 3]
    if not raw:
        return ["medical research"]

    # Keep signal terms; remove weak visual-description fillers.
    tokens: list[str] = []
    seen: set[str] = set()
    for t in raw:
        if t in _IMAGE_QUERY_GENERIC_TERMS:
            continue
        if t in seen:
            continue
        seen.add(t)
        tokens.append(t)

    if not tokens:
        tokens = raw[:3]

    out: list[str] = []

    if "smoking" in tokens and ("lung" in tokens or "pulmonary" in tokens):
        out.append("smoking lung disease")

    if len(tokens) >= 2:
        out.append(f"{tokens[0]} {tokens[1]}")
        out.append(f"{tokens[0]} {tokens[1]} treatment")
    if len(tokens) >= 3:
        out.append(" ".join(tokens[:3]))

    if "cancer" in tokens and "lung" in tokens:
        out.append("lung cancer treatment")

    out.append(" ".join(tokens[:2]) if len(tokens) >= 2 else tokens[0])
    out.append("medical research")

    # Dedupe while preserving order and skipping the exact original query.
    final: list[str] = []
    q0 = (query or "").strip().lower()
    seen_q: set[str] = set()
    for cand in out:
        s = " ".join(cand.split()).strip()
        if not s:
            continue
        sl = s.lower()
        if sl == q0 or sl in seen_q:
            continue
        seen_q.add(sl)
        final.append(s)
    return final


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, origins=settings.cors_allow_origins, supports_credentials=True)

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True})

    @app.get("/api/capabilities")
    def capabilities():
        return jsonify(
            {
                "service": "MedRAG API",
                "version": "1",
                "endpoints": [
                    {
                        "path": "/api/analyze",
                        "method": "POST",
                        "description": "Primary text-query retrieval endpoint with optional metadata filters.",
                    },
                    {
                        "path": "/api/query/document",
                        "method": "POST multipart/form-data",
                        "description": "Extracts text from uploaded document (txt/pdf/docx) and runs analysis.",
                    },
                    {
                        "path": "/api/query/image",
                        "method": "POST multipart/form-data",
                        "description": "Extracts text from uploaded image/screenshot and runs analysis.",
                    },
                    {
                        "path": "/api/query/audio",
                        "method": "POST multipart/form-data",
                        "description": "Transcribes uploaded audio discussion and runs analysis.",
                    },
                    {
                        "path": "/api/metadata/options",
                        "method": "GET",
                        "description": "Returns filter metadata (year range, journal, disease area, trial stage, study type).",
                    },
                    {
                        "path": "/api/paper/<pmid>",
                        "method": "GET",
                        "description": "Returns full stored metadata for a specific article.",
                    },
                    {
                        "path": "/api/related/<pmid>",
                        "method": "GET",
                        "description": "Finds related papers using the selected paper as query context.",
                    },
                ],
                "analyze_request_example": {
                    "query": "Non-invasive therapy for knee arthritis",
                    "filters": {
                        "publication_year_from": 2022,
                        "publication_year_to": 2026,
                        "journal": "The Lancet",
                        "disease_area": "Arthritis",
                        "study_type": "Randomized Controlled Trial",
                    },
                    "rerank": True,
                    "include_insights": True,
                },
                "analyze_response_fields": [
                    "results[].citation (pmid, title, journal, year, authors, doi)",
                    "results[].evidence (supporting snippets)",
                    "results[].key_points (per-article distilled points)",
                    "insights.summary / insights.key_findings (cross-paper evidence synthesis)",
                    "guardrails (query/data-quality caveats)",
                ],
            }
        )

    @app.post("/api/analyze")
    def analyze():
        payload = request.get_json(silent=True) or {}
        try:
            resp = run_multi_agent_analysis(payload)
        except Exception as e:  # noqa: BLE001
            return jsonify({"detail": str(e)}), 400
        return jsonify(resp)

    @app.get("/api/metadata/options")
    def metadata_options():
        with db_conn(settings.db_path) as conn:
            migrate(conn)
            years = conn.execute("SELECT MIN(year) AS min_y, MAX(year) AS max_y FROM papers").fetchone()
            journals = [
                r["journal"]
                for r in conn.execute(
                    "SELECT journal FROM papers WHERE journal IS NOT NULL AND journal != '' GROUP BY journal ORDER BY COUNT(1) DESC LIMIT 200"
                ).fetchall()
            ]
            disease_areas = [
                r["disease_area"]
                for r in conn.execute(
                    "SELECT disease_area FROM papers WHERE disease_area IS NOT NULL AND disease_area != '' GROUP BY disease_area ORDER BY COUNT(1) DESC LIMIT 200"
                ).fetchall()
            ]
            trial_stages = [
                r["trial_stage"]
                for r in conn.execute(
                    "SELECT trial_stage FROM papers WHERE trial_stage IS NOT NULL AND trial_stage != '' GROUP BY trial_stage ORDER BY trial_stage"
                ).fetchall()
            ]
            pub_types: dict[str, int] = {}
            for r in conn.execute("SELECT publication_types_json FROM papers LIMIT 5000").fetchall():
                for t in json.loads(r["publication_types_json"] or "[]"):
                    if not t:
                        continue
                    pub_types[t] = pub_types.get(t, 0) + 1
            top_pub_types = [k for k, _ in sorted(pub_types.items(), key=lambda kv: kv[1], reverse=True)[:120]]

            return jsonify(
                {
                    "years": {"min": years["min_y"], "max": years["max_y"]},
                    "journals": journals,
                    "disease_areas": disease_areas,
                    "trial_stages": trial_stages,
                    "study_types": top_pub_types,
                }
            )

    @app.get("/api/paper/<pmid>")
    def get_paper(pmid: str):
        with db_conn(settings.db_path) as conn:
            migrate(conn)
            r = conn.execute(
                """
                SELECT pmid,title,abstract,year,journal,authors_json,mesh_terms_json,keywords_json,publication_types_json,doi,
                       disease_area,trial_stage
                FROM papers
                WHERE pmid = ?
                """,
                (pmid,),
            ).fetchone()
            if not r:
                return jsonify({"detail": "PMID not found"}), 404
            return jsonify(dict(r))

    @app.get("/api/related/<pmid>")
    def related(pmid: str):
        with db_conn(settings.db_path) as conn:
            migrate(conn)
            r = conn.execute("SELECT title, abstract FROM papers WHERE pmid = ?", (pmid,)).fetchone()
            if not r:
                return jsonify({"detail": "PMID not found"}), 404
        # Use the article itself as the "query" to find similar papers.
        payload = {"query": f"{r['title']}\n\n{r['abstract']}", "rerank": True, "include_insights": False}
        try:
            resp = run_multi_agent_analysis(payload)
        except Exception as e:  # noqa: BLE001
            return jsonify({"detail": str(e)}), 400
        resp["results"] = [x for x in (resp.get("results") or []) if x.get("pmid") != pmid]
        return jsonify(resp)

    @app.post("/api/query/document")
    def analyze_document():
        if "file" not in request.files:
            return jsonify({"detail": "Missing multipart file field: file"}), 400
        f = request.files["file"]
        data = f.read()
        try:
            text = extract_text_from_document(f.filename or "upload", data)
            mode = (request.args.get("mode") or "simple").strip().lower()
            if mode == "full":
                query_text = text
            elif mode == "keywords":
                query_text = compact_query_from_text(text)
            else:
                query_text = simple_query_from_text(text) or compact_query_from_text(text)
            resp = run_multi_agent_analysis(
                {
                    "query": query_text,
                    "rerank": request.args.get("rerank", "true").lower() != "false",
                    "include_insights": request.args.get("include_insights", "true").lower() != "false",
                }
            )
        except Exception as e:  # noqa: BLE001
            return jsonify({"detail": str(e)}), 400
        return jsonify(resp)

    @app.post("/api/query/image")
    def analyze_image():
        if "file" not in request.files:
            return jsonify({"detail": "Missing multipart file field: file"}), 400
        f = request.files["file"]
        data = f.read()
        try:
            query_text = infer_query_from_image(f.filename or "upload", data)
            rerank = request.args.get("rerank", "true").lower() != "false"
            include_insights = request.args.get("include_insights", "true").lower() != "false"
            resp = run_multi_agent_analysis(
                {
                    "query": query_text,
                    "rerank": rerank,
                    "include_insights": include_insights,
                }
            )
            if not (resp.get("results") or []):
                for alt in _image_query_fallbacks(query_text):
                    trial = run_multi_agent_analysis(
                        {
                            "query": alt,
                            "rerank": rerank,
                            "include_insights": include_insights,
                        }
                    )
                    if trial.get("results"):
                        resp = trial
                        break
        except Exception as e:  # noqa: BLE001
            return jsonify({"detail": str(e)}), 400
        return jsonify(resp)

    @app.post("/api/query/audio")
    def analyze_audio():
        if "file" not in request.files:
            return jsonify({"detail": "Missing multipart file field: file"}), 400
        f = request.files["file"]
        data = f.read()
        try:
            text = extract_text_from_audio(f.filename or "upload", data)
            resp = run_multi_agent_analysis(
                {
                    "query": text,
                    "rerank": request.args.get("rerank", "true").lower() != "false",
                    "include_insights": request.args.get("include_insights", "true").lower() != "false",
                }
            )
        except Exception as e:  # noqa: BLE001
            return jsonify({"detail": str(e)}), 400
        return jsonify(resp)

    return app


app = create_app()


def _run_dev_server() -> None:
    # Keep this simple and dependency-free: Flask's dev server is enough for local demos.
    host = os.getenv("MEDRAG_HOST", "127.0.0.1")
    port = int(os.getenv("MEDRAG_PORT", os.getenv("PORT", "8000")))
    debug = os.getenv("MEDRAG_DEBUG", "1").strip().lower() in ("1", "true", "yes", "y", "on")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    _run_dev_server()


