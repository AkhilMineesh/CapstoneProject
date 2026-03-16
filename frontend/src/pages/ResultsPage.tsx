import { useMemo, useState } from 'react'
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

export default function ResultsPage() {
  const { chatId } = useParams()
  const { getChat } = useChats()
  const chat = useMemo(() => (chatId ? getChat(chatId) : null), [chatId, getChat])
  const results = chat?.response.results ?? []
  const maxS = useMemo(() => maxScore(results), [results])

  const [selected, setSelected] = useState<PaperResult | null>(null)
  const [q, setQ] = useState('')

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return results
    return results.filter((r) => `${r.title} ${r.abstract} ${r.citation.journal ?? ''}`.toLowerCase().includes(needle))
  }, [q, results])

  if (!chat) {
    return (
      <div className="main">
        <header className="topbar">
          <button className="iconBtn mobileOnly" type="button" aria-label="Open sidebar" onClick={() => window.dispatchEvent(new CustomEvent('medrag:openSidebar'))}>
            ☰
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
        <button className="iconBtn mobileOnly" type="button" aria-label="Open sidebar" onClick={() => window.dispatchEvent(new CustomEvent('medrag:openSidebar'))}>
          ☰
        </button>
        <div className="topTitle">
          <div className="h1">Results</div>
          <div className="sub ellipsis" title={chat.request.query}>
            {chat.request.query}
          </div>
        </div>
        <div className="topActions">
          <Link className="btn secondary" to={`/chat/${chat.id}`}>
            Back to chat
          </Link>
        </div>
      </header>

      <div className="resultsWrap">
        <div className="resultsHead">
          <div className="resultsCount">
            <span className="pill">{filtered.length} articles</span>
            <span className="pill subtle">Click a card for overview</span>
          </div>
          <input
            className="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search within results…"
          />
        </div>

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
                  {r.citation.year ? <span>• {r.citation.year}</span> : null}
                  <span>• PMID {r.pmid}</span>
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

      <ArticleModal
        open={!!selected}
        paper={selected}
        query={chat.request.query}
        maxScore={maxS}
        onClose={() => setSelected(null)}
      />
    </div>
  )
}

