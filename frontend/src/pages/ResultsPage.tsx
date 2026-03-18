import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ArticleModal from '../components/ArticleModal'
import type { PaperResult } from '../api'
import { useChats } from '../state/chats'

function maxScore(results: PaperResult[]): number {
  return results.reduce((m, r) => Math.max(m, r.score || 0), 0) || 1
}

function pct(score: number, max: number): number {
  return Math.max(0, Math.min(100, Math.round((score / max) * 100)))
}

function splitFinding(line: string): { content: string; reference: string } {
  const raw = (line || '').trim()
  if (!raw) return { content: '', reference: '' }
  const idx = raw.indexOf(':')
  if (idx > 0) {
    return {
      reference: raw.slice(0, idx).trim(),
      content: raw.slice(idx + 1).trim(),
    }
  }
  return { content: raw, reference: raw }
}

export default function ResultsPage() {
  const { chatId } = useParams()
  const { getChat } = useChats()
  const chat = useMemo(() => (chatId ? getChat(chatId) : null), [chatId, getChat])
  const results = chat?.response.results ?? []
  const insights = chat?.response.insights
  const maxS = useMemo(() => maxScore(results), [results])

  const [selected, setSelected] = useState<PaperResult | null>(null)
  const [q, setQ] = useState('')
  const [insightExpanded, setInsightExpanded] = useState(false)

  useEffect(() => {
    setInsightExpanded(false)
  }, [chat?.id])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const base = needle
      ? results.filter((r) => `${r.title} ${r.abstract} ${r.citation.journal ?? ''}`.toLowerCase().includes(needle))
      : results
    return [...base].sort((a, b) => (b.score || 0) - (a.score || 0))
  }, [q, results])

  const findingParts = useMemo(
    () => (insights?.key_findings ?? []).slice(0, 5).map((k) => splitFinding(k)),
    [insights?.key_findings],
  )

  if (!chat) {
    return (
      <div className="main">
        <header className="topbar">
          <button
            className="iconBtn mobileOnly"
            type="button"
            aria-label="Open sidebar"
            onClick={() => window.dispatchEvent(new CustomEvent('MedAssist:openSidebar'))}
          >
            Menu
          </button>
          <div className="topTitle">
            <div className="h1">Results</div>
            <div className="sub">Chat not found.</div>
          </div>
          <Link className="btn secondary" to="/">
            Back
          </Link>
        </header>
        <div className="centerEmpty">Select a chat from the left, or start a new one.</div>
      </div>
    )
  }

  return (
    <div className="main">
      <header className="topbar">
        <button
          className="iconBtn mobileOnly"
          type="button"
          aria-label="Open sidebar"
          onClick={() => window.dispatchEvent(new CustomEvent('MedAssist:openSidebar'))}
        >
          Menu
        </button>
        <div className="topTitle">
          <div className="h1">Results</div>
          <div className="sub ellipsis" title={chat.request.query}>
            {chat.request.query}
          </div>
        </div>
        <div className="topActions">
          <Link className="btn secondary" to={`/chat/${chat.id}`}>
            Return to chat
          </Link>
        </div>
      </header>

      <div className="resultsWrap">
        <div className="resultsHead">
          <div className="resultsCount">
            <span className="resultCountHero">{filtered.length} results found!</span>
          </div>
          <input
            className="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search within results..."
          />
        </div>

        {insights ? (
          <div className="bubble assistant" style={{ marginBottom: 12 }}>
            <button
              className="summaryToggle"
              type="button"
              onClick={() => setInsightExpanded((v) => !v)}
              aria-expanded={insightExpanded}
            >
              <span className="bubbleTitle noGap">Evidence summary</span>
              <span className="summaryToggleText" aria-hidden="true">
                {insightExpanded ? '▾' : '▸'}
              </span>
            </button>
            {insightExpanded ? (
              <>
                {findingParts.length ? (
                  <div className="smallMuted insightList">
                    {findingParts.map((f) => (
                      <div key={`${f.reference}|${f.content}`}>- {f.content}</div>
                    ))}
                  </div>
                ) : null}
                {findingParts.length ? (
                  <div className="smallMuted insightList" style={{ marginTop: 10 }}>
                    <div className="bubbleTitle noGap">References</div>
                    {findingParts.map((f) => (
                      <div key={`${f.reference}|ref`}>- {f.reference}</div>
                    ))}
                  </div>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}

        <div className="cards">
          {filtered.map((r) => {
            const m = pct(r.score, maxS)
            return (
              <button key={r.pmid} className="card" type="button" onClick={() => setSelected(r)}>
                <div className="cardTop">
                  <div className="cardTitle">{r.title}</div>
                  <div className="matchPill" aria-label={`Match ${m} percent`}>
                    {m}%
                  </div>
                </div>
                <div className="cardMeta">
                  <span>{r.citation.journal ?? 'Journal n/a'}</span>
                  {r.citation.year ? <span> - {r.citation.year}</span> : null}
                  <span> - PMID {r.pmid}</span>
                </div>
                <div className="barTrack" aria-hidden="true">
                  <div className="barFill" style={{ width: `${m}%` }} />
                </div>
                <div className="cardAbstract">{r.abstract}</div>
              </button>
            )
          })}
          {!filtered.length ? <div className="centerEmpty">No matches for that search.</div> : null}
        </div>
      </div>

      <ArticleModal open={!!selected} paper={selected} query={chat.request.query} maxScore={maxS} onClose={() => setSelected(null)} />
    </div>
  )
}

