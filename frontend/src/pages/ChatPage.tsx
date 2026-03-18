import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { analyzeFile, metadataOptions, type Filters, type SearchRequest } from '../api'
import { useChats } from '../state/chats'

type FileKind = 'document' | 'image' | 'audio'

export default function ChatPage() {
  const { chatId } = useParams()
  const nav = useNavigate()
  const { getChat, createChatFromQuery, createChatFromResponse, setActiveChatId } = useChats()
  const activeChat = useMemo(() => (chatId ? getChat(chatId) : null), [chatId, getChat])

  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showOptions, setShowOptions] = useState(false)

  const [yearFrom, setYearFrom] = useState<number | ''>('')
  const [yearTo, setYearTo] = useState<number | ''>('')
  const [journal, setJournal] = useState('')
  const [diseaseArea, setDiseaseArea] = useState('')
  const [studyType, setStudyType] = useState('')
  const [rerank, setRerank] = useState(true)
  const [insights, setInsights] = useState(false)

  const [journals, setJournals] = useState<string[]>([])
  const [diseaseAreas, setDiseaseAreas] = useState<string[]>([])
  const [studyTypes, setStudyTypes] = useState<string[]>([])
  const [yearMin, setYearMin] = useState<number | null>(null)
  const [yearMax, setYearMax] = useState<number | null>(null)

  const docInputRef = useRef<HTMLInputElement | null>(null)
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  const audioInputRef = useRef<HTMLInputElement | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const [recording, setRecording] = useState(false)
  const introFullText = 'Welcome to MedAssist Research Assistant'
  const introPrefix = 'Welcome to '
  const introBrand = 'MedAssist Research Assistant'
  const [introPhase, setIntroPhase] = useState<'typing' | 'move' | 'done'>('typing')
  const [typedLen, setTypedLen] = useState(0)

  useEffect(() => {
    let mounted = true
    void metadataOptions()
      .then((m) => {
        if (!mounted) return
        setJournals(m.journals || [])
        setDiseaseAreas(m.disease_areas || [])
        setStudyTypes(m.study_types || [])
        setYearMin(m.years?.min ?? null)
        setYearMax(m.years?.max ?? null)
      })
      .catch(() => {
        // keep defaults
      })
    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    if (activeChat) {
      setQuery(activeChat.request.query)
      setError(null)
    } else {
      setQuery('')
      setError(null)
    }
  }, [activeChat?.id])

  useEffect(() => {
    if (activeChat) {
      setIntroPhase('done')
      setTypedLen(introFullText.length)
      return
    }
    if (introPhase !== 'typing') return
    if (typedLen >= introFullText.length) {
      const moveTimer = window.setTimeout(() => setIntroPhase('move'), 260)
      return () => window.clearTimeout(moveTimer)
    }
    const timer = window.setTimeout(() => setTypedLen((n) => Math.min(n + 1, introFullText.length)), 40)
    return () => window.clearTimeout(timer)
  }, [activeChat, introPhase, typedLen])

  useEffect(() => {
    if (introPhase !== 'move') return
    const doneTimer = window.setTimeout(() => setIntroPhase('done'), 760)
    return () => window.clearTimeout(doneTimer)
  }, [introPhase])
  function buildFilters(): Filters {
    const filters: Filters = {}
    if (yearFrom !== '') filters.publication_year_from = Number(yearFrom)
    if (yearTo !== '') filters.publication_year_to = Number(yearTo)
    if (journal.trim()) filters.journal = journal.trim()
    if (diseaseArea.trim()) filters.disease_area = diseaseArea.trim()
    if (studyType.trim()) filters.study_type = studyType.trim()
    return filters
  }

  async function onSend() {
    const q = query.trim()
    if (!q || busy) return
    setError(null)
    setBusy(true)
    try {
      const chat = await createChatFromQuery(q, {
        filters: buildFilters(),
        rerank,
        includeInsights: insights,
      })
      setActiveChatId(chat.id)
      nav(`/chat/${chat.id}/results`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function onUpload(kind: FileKind, file: File | null) {
    if (!file || busy) return
    setError(null)
    setBusy(true)
    try {
      const resp = await analyzeFile(kind, file, { rerank, include_insights: insights })
      const fallbackQuery = kind === 'document' ? 'Uploaded document' : kind === 'image' ? 'Uploaded image/screenshot' : 'Uploaded audio discussion'
      const derivedQuery = (resp.query || '').trim() || fallbackQuery
      const req: SearchRequest = {
        query: derivedQuery,
        filters: buildFilters(),
        rerank,
        include_insights: insights,
      }
      setQuery(derivedQuery)
      const chat = createChatFromResponse(req, resp, derivedQuery)
      setActiveChatId(chat.id)
      nav(`/chat/${chat.id}/results`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser does not support microphone recording.')
      return
    }
    setError(null)
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaStreamRef.current = stream
    const rec = new MediaRecorder(stream)
    mediaRecorderRef.current = rec
    chunksRef.current = []
    rec.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data)
    }
    rec.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' })
      const ext = rec.mimeType.includes('mp4') ? 'm4a' : 'webm'
      const file = new File([blob], `voice_query.${ext}`, { type: rec.mimeType || 'audio/webm' })
      const streamToClose = mediaStreamRef.current
      if (streamToClose) {
        for (const t of streamToClose.getTracks()) t.stop()
      }
      mediaStreamRef.current = null
      mediaRecorderRef.current = null
      chunksRef.current = []
      setRecording(false)
      void onUpload('audio', file)
    }
    rec.start()
    setRecording(true)
  }

  function stopRecording() {
    const rec = mediaRecorderRef.current
    if (rec && rec.state !== 'inactive') rec.stop()
  }

  async function onMicToggle() {
    if (busy) return
    try {
      if (recording) stopRecording()
      else await startRecording()
    } catch (e) {
      const streamToClose = mediaStreamRef.current
      if (streamToClose) {
        for (const t of streamToClose.getTracks()) t.stop()
      }
      mediaStreamRef.current = null
      mediaRecorderRef.current = null
      chunksRef.current = []
      setRecording(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  function applySuggestedPrompt(text: string) {
    setQuery(text)
    ;(document.getElementById('composer') as HTMLTextAreaElement | null)?.focus()
  }
  function landingHeader() {
    return (
      <div className="landingHeader">
        <div className="landingTitle">MedAssist Research Assistant</div>
        <div className="landingSubtitle">Search biomedical evidence with multimodal input, hybrid retrieval, and citation-backed summaries in one modern workflow.</div>
      </div>
    )
  }

  function introHeader() {
    const typedText = introFullText.slice(0, typedLen)
    const prefixTypedLen = Math.min(typedText.length, introPrefix.length)
    const brandTypedLen = Math.max(typedText.length - introPrefix.length, 0)
    const shownPrefix = introPrefix.slice(0, prefixTypedLen)
    const shownBrand = introBrand.slice(0, brandTypedLen)
    return (
      <div className={`introStage phase-${introPhase}`}>
        <div className="introLine" aria-live="polite">
          <span className="introPrefix">{shownPrefix}</span>
          <span className="introBrand">{shownBrand}</span>
        </div>
        <div className="introLandingHeader">{landingHeader()}</div>
      </div>
    )
  }

  function composer(classes: string) {
    return (
      <div className={classes}>
        <div className="composerTop">
          <button className="btn ghost" type="button" onClick={() => setShowOptions((s) => !s)}>
            Filters
          </button>
          {showOptions ? (
            <div className="opts">
              <label className="opt">
                <span>Year from</span>
                <input
                  type="number"
                  value={yearFrom}
                  min={yearMin ?? undefined}
                  max={yearMax ?? undefined}
                  placeholder={yearMin ? `${yearMin}` : 'optional'}
                  onChange={(e) => setYearFrom(e.target.value ? Number(e.target.value) : '')}
                />
              </label>
              <label className="opt">
                <span>Year to</span>
                <input
                  type="number"
                  value={yearTo}
                  min={yearMin ?? undefined}
                  max={yearMax ?? undefined}
                  placeholder={yearMax ? `${yearMax}` : 'optional'}
                  onChange={(e) => setYearTo(e.target.value ? Number(e.target.value) : '')}
                />
              </label>
              <label className="opt">
                <span>Journal</span>
                <select value={journal} onChange={(e) => setJournal(e.target.value)}>
                  <option value="">All journals</option>
                  {journals.slice(0, 120).map((j) => (
                    <option key={j} value={j}>
                      {j}
                    </option>
                  ))}
                </select>
              </label>
              <label className="opt">
                <span>Disease area</span>
                <select value={diseaseArea} onChange={(e) => setDiseaseArea(e.target.value)}>
                  <option value="">All disease areas</option>
                  {diseaseAreas.slice(0, 120).map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </label>
              <label className="opt">
                <span>Study type</span>
                <select value={studyType} onChange={(e) => setStudyType(e.target.value)}>
                  <option value="">All study categories</option>
                  {studyTypes.slice(0, 120).map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
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
          <div className="textareaWrap">
            <textarea
              id="composer"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type your medical research prompt (or use uploads and voice)"
              rows={2}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void onSend()
                }
              }}
            />
            <button
              className={`iconBtn micBtn${recording ? ' recording' : ''}`}
              type="button"
              disabled={busy}
              aria-label={recording ? 'Stop microphone recording' : 'Start microphone recording'}
              title={recording ? 'Stop microphone recording' : 'Start microphone recording'}
              onClick={() => void onMicToggle()}
            >
              {'\u{1F3A4}'}
            </button>
          </div>
          <button className="btn" type="button" onClick={onSend} disabled={busy || !query.trim()}>
            {busy ? 'Searching...' : 'Search'}
          </button>
        </div>

        <div className="bubbleActions uploaderRow">
          <input
            ref={docInputRef}
            type="file"
            accept=".txt,.pdf,.doc,.docx"
            style={{ display: 'none' }}
            onChange={(e) => void onUpload('document', e.target.files?.[0] ?? null)}
          />
          <input
            ref={imageInputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => void onUpload('image', e.target.files?.[0] ?? null)}
          />
          <input
            ref={audioInputRef}
            type="file"
            accept="audio/*"
            style={{ display: 'none' }}
            onChange={(e) => void onUpload('audio', e.target.files?.[0] ?? null)}
          />
          <button className="btn secondary" type="button" disabled={busy} onClick={() => docInputRef.current?.click()}>
            Document
          </button>
          <button className="btn secondary" type="button" disabled={busy} onClick={() => imageInputRef.current?.click()}>
            Image
          </button>
          <button className="btn secondary" type="button" disabled={busy} onClick={() => audioInputRef.current?.click()}>
            Audio file
          </button>
        </div>

        <div className="smallMuted">Enter to send | Shift+Enter newline | Use simple queries and avoid overly complex prompts | Search opens results</div>
      </div>
    )
  }

  return (
    <div className={!activeChat ? 'main landingMain' : 'main'}>
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
          {activeChat ? (
            <>
              <div className="h1">MedAssist Research Chat</div>
              <div className="sub">Refine your query, then open the updated results.</div>
            </>
          ) : (
            <></>
          )}
        </div>
        <div className="topActions">
          {activeChat ? (
            <Link className="btn secondary" to={`/chat/${activeChat.id}/results`}>
              Return to results
            </Link>
          ) : null}
        </div>
      </header>
      <div className="chatArea">
        {!activeChat ? (
          <div className="welcome landing">
            <div className="landingStack">
              {introPhase === 'done' ? landingHeader() : introHeader()}
              <div className="recommendedLabel">Recommended prompts</div>
              <div className="recommendedPrompts">
                {[
                  'Latest treatments for early-stage pancreatic cancer',
                  'Non-invasive therapy for knee arthritis',
                  'mRNA vaccine studies published after 2022',
                ].map((ex) => (
                  <button key={ex} className="chip" type="button" onClick={() => applySuggestedPrompt(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
              {composer('composer landingComposer centerComposer')}
            </div>
          </div>
        ) : (
          <div className="welcome">
            <div className="landingStack">{composer('composer landingComposer centerComposer')}</div>
          </div>
        )}
      </div>
    </div>
  )
}











