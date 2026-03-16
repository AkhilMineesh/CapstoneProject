import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { Filters } from '../api'
import { useChats } from '../state/chats'

export default function ChatPage() {
  const { chatId } = useParams()
  const nav = useNavigate()
  const { getChat, createChatFromQuery, setActiveChatId } = useChats()

  const activeChat = useMemo(() => (chatId ? getChat(chatId) : null), [chatId, getChat])

  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showOptions, setShowOptions] = useState(false)
  const [yearFrom, setYearFrom] = useState<number | ''>('')
  const [rerank, setRerank] = useState(true)
  const [insights, setInsights] = useState(true)

  async function onSend() {
    const q = query.trim()
    if (!q || busy) return
    setError(null)
    setBusy(true)
    try {
      const filters: Filters = {}
      if (yearFrom !== '') filters.publication_year_from = Number(yearFrom)
      const chat = await createChatFromQuery(q, {
        filters,
        rerank,
        includeInsights: insights,
      })
      setActiveChatId(chat.id)
      setQuery('')
      nav(`/chat/${chat.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="main">
      <header className="topbar">
        <button className="iconBtn mobileOnly" type="button" aria-label="Open sidebar" onClick={() => window.dispatchEvent(new CustomEvent('medrag:openSidebar'))}>
          ☰
        </button>
        <div className="topTitle">
          <div className="h1">MedRAG Research Chat</div>
          <div className="sub">Ask for abstracts and evidence snippets (not clinical guidance).</div>
        </div>
        {activeChat ? (
          <Link className="btn secondary" to={`/chat/${activeChat.id}/results`}>
            View results
          </Link>
        ) : (
          <div />
        )}
      </header>

      <div className="chatArea">
        {!activeChat ? (
          <div className="welcome">
            <div className="bubble assistant">
              <div className="bubbleTitle">Assistant</div>
              <div className="bubbleText">
                Ask a medical research question and I’ll analyze the query to return only the most relevant abstracts, with a quick overview and match score.
              </div>
              <div className="chips">
                {[
                  'Latest treatments for early-stage pancreatic cancer',
                  'Non-invasive therapy for knee arthritis',
                  'mRNA vaccine studies published after 2022',
                ].map((ex) => (
                  <button
                    key={ex}
                    className="chip"
                    type="button"
                    onClick={() => {
                      setQuery(ex)
                      ;(document.getElementById('composer') as HTMLTextAreaElement | null)?.focus()
                    }}
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="thread">
            {activeChat.messages.map((m) => (
              <div key={m.id} className={m.role === 'user' ? 'bubble user' : 'bubble assistant'}>
                <div className="bubbleTitle">{m.role === 'user' ? 'You' : 'Assistant'}</div>
                <div className="bubbleText pre">{m.text}</div>
              </div>
            ))}

            <div className="bubble assistant">
              <div className="bubbleTitle">Assistant</div>
              <div className="bubbleText">
                I found <strong>{activeChat.response.results.length}</strong> relevant articles. Click "View results" to browse, filter, and open an overview pop-up for each paper.
              </div>
              <div className="bubbleActions">
                <Link className="btn" to={`/chat/${activeChat.id}/results`}>
                  Open results
                </Link>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="composer">
        <div className="composerTop">
          <button className="btn ghost" type="button" onClick={() => setShowOptions((s) => !s)}>
            Options
          </button>
          {showOptions ? (
            <div className="opts">
              <label className="opt">
                <span>Year from</span>
                <input
                  type="number"
                  value={yearFrom}
                  placeholder="(optional)"
                  onChange={(e) => setYearFrom(e.target.value ? Number(e.target.value) : '')}
                />
              </label>
              <label className="check">
                <input type="checkbox" checked={rerank} onChange={(e) => setRerank(e.target.checked)} /> Re-rank
              </label>
              <label className="check">
                <input type="checkbox" checked={insights} onChange={(e) => setInsights(e.target.checked)} /> Insights
              </label>
            </div>
          ) : null}
        </div>

        {error ? <div className="errorBanner">Error: {error}</div> : null}

        <div className="composerRow">
          <textarea
            id="composer"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about medical research (e.g., “knee osteoarthritis exercise therapy”)"
            rows={2}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void onSend()
              }
            }}
          />
          <button className="btn" type="button" onClick={onSend} disabled={busy || !query.trim()}>
            {busy ? 'Running…' : 'Send'}
          </button>
        </div>
        <div className="smallMuted">Tip: Press Enter to send • Shift+Enter for a new line</div>
      </div>
    </div>
  )
}
