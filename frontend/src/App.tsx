import './App.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { analyze, analyzeFile, metadataOptions, type AnalyzeResponse, type Filters } from './api'

type Mode = 'text' | 'document' | 'image' | 'audio'

function App() {
  const [mode, setMode] = useState<Mode>('text')
  const [query, setQuery] = useState('Latest treatments for early-stage pancreatic cancer')
  const [filters, setFilters] = useState<Filters>({ publication_year_from: 2022 })
  const [topK, setTopK] = useState(20)
  const [rerank, setRerank] = useState(true)
  const [includeInsights, setIncludeInsights] = useState(true)
  const [file, setFile] = useState<File | null>(null)

  const [opts, setOpts] = useState<{
    years?: { min: number | null; max: number | null }
    journals: string[]
    disease_areas: string[]
    trial_stages: string[]
    study_types: string[]
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<AnalyzeResponse | null>(null)

  const rec = useRef<MediaRecorder | null>(null)
  const [recState, setRecState] = useState<'idle' | 'recording' | 'ready'>('idle')
  const [recBlob, setRecBlob] = useState<Blob | null>(null)

  useEffect(() => {
    metadataOptions()
      .then(setOpts)
      .catch(() => {
        setOpts({
          journals: [],
          disease_areas: [],
          trial_stages: [],
          study_types: [],
          years: { min: null, max: null },
        })
      })
  }, [])

  const canRun = useMemo(() => {
    if (mode === 'text') return query.trim().length > 0
    if (mode === 'audio' && recBlob) return true
    return !!file
  }, [mode, query, file, recBlob])

  async function run() {
    setError(null)
    setLoading(true)
    setData(null)
    try {
      if (mode === 'text') {
        const resp = await analyze({
          query,
          filters: Object.keys(filters).length ? filters : null,
          top_k: topK,
          rerank,
          include_insights: includeInsights,
        })
        setData(resp)
      } else if (mode === 'audio' && recBlob) {
        const f = new File([recBlob], 'voice.wav', { type: recBlob.type || 'audio/wav' })
        const resp = await analyzeFile('audio', f, { rerank, include_insights: includeInsights })
        setData(resp)
      } else if (file) {
        const kind = mode === 'document' ? 'document' : mode === 'image' ? 'image' : 'audio'
        const resp = await analyzeFile(kind, file, { rerank, include_insights: includeInsights })
        setData(resp)
      } else {
        throw new Error('Missing input')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  async function startRecording() {
    setError(null)
    setRecBlob(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const chunks: BlobPart[] = []
      const mr = new MediaRecorder(stream)
      rec.current = mr
      mr.ondataavailable = (evt) => {
        if (evt.data && evt.data.size > 0) chunks.push(evt.data)
      }
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks, { type: mr.mimeType || 'audio/webm' })
        setRecBlob(blob)
        setRecState('ready')
      }
      mr.start()
      setRecState('recording')
    } catch {
      setError('Microphone permission denied or unsupported browser. Upload an audio file instead.')
    }
  }

  function stopRecording() {
    if (rec.current && recState === 'recording') rec.current.stop()
  }

  const graph = data?.insights?.knowledge_graph ?? null
  const topEdges = useMemo(() => {
    if (!graph) return []
    return [...graph.edges]
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 14)
      .map((e) => ({
        ...e,
        sourceLabel: graph.nodes.find((n) => n.id === e.source)?.label ?? e.source,
        targetLabel: graph.nodes.find((n) => n.id === e.target)?.label ?? e.target,
      }))
  }, [graph])

  return (
    <div className="page">
      <header className="top">
        <div className="brand">
          <div className="mark" aria-hidden="true">
            MR
          </div>
          <div>
            <div className="title">MedRAG Research Explorer</div>
            <div className="tag">
              Hybrid retrieval (vector + keyword), re-ranking, MeSH expansion, and multi-agent abstract analysis.
            </div>
          </div>
        </div>
        <div className="status">
          <span className="pill">API: /api/analyze</span>
          <span className="pill subtle">Dataset: PubMed/MEDLINE abstracts</span>
        </div>
      </header>

      <main className="grid">
        <section className="panel">
          <div className="panelHeader">
            <h2>Query</h2>
            <div className="modes" role="tablist" aria-label="Query mode">
              {(['text', 'document', 'image', 'audio'] as Mode[]).map((m) => (
                <button
                  key={m}
                  role="tab"
                  aria-selected={mode === m}
                  className={mode === m ? 'mode active' : 'mode'}
                  onClick={() => {
                    setMode(m)
                    setError(null)
                    setFile(null)
                    setRecBlob(null)
                    setRecState('idle')
                  }}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          {mode === 'text' ? (
            <>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask for medical research using natural language…"
                rows={5}
              />
              <div className="hint">
                Examples: <code>Non-invasive therapy for knee arthritis</code>,{' '}
                <code>mRNA vaccine studies published after 2022</code>
              </div>
            </>
          ) : mode === 'audio' ? (
            <div className="fileBox">
              <div className="fileRow">
                <input type="file" accept="audio/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                <button className="ghost" onClick={recState === 'recording' ? stopRecording : startRecording}>
                  {recState === 'recording' ? 'Stop recording' : 'Record'}
                </button>
              </div>
              {recBlob ? <audio controls src={URL.createObjectURL(recBlob)} /> : <div className="hint">Upload or record a voice query.</div>}
            </div>
          ) : (
            <div className="fileBox">
              <input
                type="file"
                accept={mode === 'image' ? 'image/*' : undefined}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <div className="hint">
                {mode === 'document'
                  ? 'Upload a clinical note excerpt, PDF, DOCX, or plain text.'
                  : 'Upload an image containing a query (OCR).'}{' '}
                Only extracted text is used for retrieval.
              </div>
            </div>
          )}

          <div className="controls">
            <div className="toggles">
              <label className="check">
                <input type="checkbox" checked={rerank} onChange={(e) => setRerank(e.target.checked)} /> Re-rank
              </label>
              <label className="check">
                <input type="checkbox" checked={includeInsights} onChange={(e) => setIncludeInsights(e.target.checked)} /> Insights
              </label>
            </div>
            <div className="row">
              <label className="field">
                <span>Top K</span>
                <input
                  type="number"
                  min={5}
                  max={50}
                  value={topK}
                  onChange={(e) => setTopK(Math.max(5, Math.min(50, Number(e.target.value) || 20)))}
                />
              </label>
              <button className="run" disabled={!canRun || loading} onClick={run}>
                {loading ? 'Searching…' : 'Run'}
              </button>
            </div>
          </div>

          <details className="filters" open>
            <summary>Filters</summary>
            <div className="filtersGrid">
              <label className="field">
                <span>Year from</span>
                <input
                  type="number"
                  value={filters.publication_year_from ?? ''}
                  placeholder={String(opts?.years?.min ?? '')}
                  onChange={(e) =>
                    setFilters((f) => ({
                      ...f,
                      publication_year_from: e.target.value ? Number(e.target.value) : undefined,
                    }))
                  }
                />
              </label>
              <label className="field">
                <span>Year to</span>
                <input
                  type="number"
                  value={filters.publication_year_to ?? ''}
                  placeholder={String(opts?.years?.max ?? '')}
                  onChange={(e) =>
                    setFilters((f) => ({
                      ...f,
                      publication_year_to: e.target.value ? Number(e.target.value) : undefined,
                    }))
                  }
                />
              </label>
              <label className="field">
                <span>Journal</span>
                <input
                  list="journals"
                  value={filters.journal ?? ''}
                  placeholder="Any"
                  onChange={(e) => setFilters((f) => ({ ...f, journal: e.target.value || undefined }))}
                />
                <datalist id="journals">
                  {(opts?.journals ?? []).map((j) => (
                    <option key={j} value={j} />
                  ))}
                </datalist>
              </label>
              <label className="field">
                <span>Study type</span>
                <input
                  list="studytypes"
                  value={filters.study_type ?? ''}
                  placeholder="Any"
                  onChange={(e) => setFilters((f) => ({ ...f, study_type: e.target.value || undefined }))}
                />
                <datalist id="studytypes">
                  {(opts?.study_types ?? []).map((t) => (
                    <option key={t} value={t} />
                  ))}
                </datalist>
              </label>
              <label className="field">
                <span>Disease area</span>
                <input
                  list="diseases"
                  value={filters.disease_area ?? ''}
                  placeholder="Any"
                  onChange={(e) => setFilters((f) => ({ ...f, disease_area: e.target.value || undefined }))}
                />
                <datalist id="diseases">
                  {(opts?.disease_areas ?? []).map((d) => (
                    <option key={d} value={d} />
                  ))}
                </datalist>
              </label>
              <label className="field">
                <span>Trial stage</span>
                <input
                  list="stages"
                  value={filters.clinical_trial_stage ?? ''}
                  placeholder="Any"
                  onChange={(e) => setFilters((f) => ({ ...f, clinical_trial_stage: e.target.value || undefined }))}
                />
                <datalist id="stages">
                  {(opts?.trial_stages ?? []).map((s) => (
                    <option key={s} value={s} />
                  ))}
                </datalist>
              </label>
            </div>
            <div className="hint">
              Filter fields map to PubMed metadata where available. Trial stage is inferred from publication type or abstract.
            </div>
          </details>

          {error ? <div className="error">Error: {error}</div> : null}
        </section>

        <section className="panel">
          <div className="panelHeader">
            <h2>Results</h2>
            <div className="meta">
              {data?.expanded_query ? (
                <span className="pill subtle" title={data.expanded_query}>
                  Expanded query (MeSH)
                </span>
              ) : null}
              {data ? <span className="pill">{data.results.length} papers</span> : <span className="pill subtle">Idle</span>}
            </div>
          </div>

          {data?.insights ? (
            <div className="insights">
              <div className="card">
                <div className="cardTitle">Research intelligence</div>
                <div className="small">{data.insights.summary}</div>
                {data.insights.guardrails?.length ? (
                  <div className="warn">
                    {data.insights.guardrails.map((w) => (
                      <div key={w}>Guardrail: {w}</div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="card">
                <div className="cardTitle">Key findings (abstract-level)</div>
                <ol className="findings">
                  {(data.insights.key_findings ?? []).slice(0, 6).map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ol>
              </div>

              {data.insights.conflicts?.length ? (
                <div className="card">
                  <div className="cardTitle">Conflicting signals</div>
                  {data.insights.conflicts.map((c) => (
                    <div key={c.outcome} className="conflict">
                      <div className="conflictTitle">{c.outcome}</div>
                      <div className="small">{c.note}</div>
                      <div className="small">
                        Supporting: {c.papers_supporting.join(', ') || 'n/a'}; Conflicting: {c.papers_conflicting.join(', ') || 'n/a'}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}

              {data.insights.trends?.length ? (
                <div className="card">
                  <div className="cardTitle">Trends</div>
                  <div className="trends">
                    {data.insights.trends.slice(0, 8).map((t) => (
                      <div key={t.term} className="trend">
                        <div className="trendTerm">{t.term}</div>
                        <div className="trendBars">
                          {Object.entries(t.counts_by_year).map(([y, c]) => (
                            <div key={y} className="bar" title={`${y}: ${c}`} style={{ flexGrow: Math.max(1, c) }}>
                              <span>{y}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {graph ? (
                <div className="card">
                  <div className="cardTitle">Knowledge graph (preview)</div>
                  <div className="small">
                    Nodes: {graph.nodes.length}, edges: {graph.edges.length}. Showing strongest edges.
                  </div>
                  <div className="edges">
                    {topEdges.map((e) => (
                      <div key={`${e.source}|${e.target}|${e.rel}`} className="edge">
                        <span className="edgeRel">{e.rel}</span>
                        <span className="edgeText">
                          {e.sourceLabel} → {e.targetLabel}
                        </span>
                        <span className="edgeW">{e.weight}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {data?.agent_reports?.length ? (
            <div className="agents">
              {data.agent_reports.map((ar) => (
                <details key={ar.agent} className="agentCard">
                  <summary>{ar.agent}</summary>
                  <ul>
                    {ar.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          ) : null}

          <div className="list">
            {data?.results?.map((r) => (
              <article key={r.pmid} className="paper">
                <div className="paperTop">
                  <div className="paperTitle">{r.title}</div>
                  <div className="paperMeta">
                    <span className="pill">{r.citation.year ?? 'n.d.'}</span>
                    {r.citation.journal ? <span className="pill subtle">{r.citation.journal}</span> : null}
                    {r.trial_stage ? <span className="pill subtle">{r.trial_stage}</span> : null}
                    <a className="pill link" href={`https://pubmed.ncbi.nlm.nih.gov/${r.pmid}/`} target="_blank" rel="noreferrer">
                      PMID {r.pmid}
                    </a>
                  </div>
                </div>
                <div className="paperAbs">{r.abstract}</div>
                {r.evidence?.length ? (
                  <div className="evidence">
                    {r.evidence.map((e) => (
                      <div key={e.text} className="ev">
                        <div className="evText">{e.text}</div>
                        <div className="evWhy">{e.why}</div>
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="chips">
                  {(r.publication_types ?? []).slice(0, 3).map((t) => (
                    <span key={t} className="chip">
                      {t}
                    </span>
                  ))}
                  {(r.mesh_terms ?? []).slice(0, 4).map((t) => (
                    <span key={t} className="chip subtle">
                      {t}
                    </span>
                  ))}
                </div>
              </article>
            ))}
            {!data && !loading ? (
              <div className="empty">
                Run a query after you ingest/index PubMed abstracts. If the backend says the index is empty, follow the README ingestion steps.
              </div>
            ) : null}
          </div>
        </section>
      </main>

      <footer className="foot">
        <div className="small">
          Abstract-level analysis only. For clinical decisions, consult guidelines, full texts, and a qualified clinician.
        </div>
      </footer>
    </div>
  )
}

export default App
