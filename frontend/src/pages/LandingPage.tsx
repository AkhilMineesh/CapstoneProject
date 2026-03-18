import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ShimmerButton from '../components/ShimmerButton'

export default function LandingPage() {
  const nav = useNavigate()
  const introText = 'Welcome to MedRAG Research Assistant'
  const [phase, setPhase] = useState<'typing' | 'move' | 'done'>('typing')
  const [typedLen, setTypedLen] = useState(0)

  useEffect(() => {
    if (phase !== 'typing') return
    if (typedLen >= introText.length) {
      const moveTimer = window.setTimeout(() => setPhase('move'), 320)
      return () => window.clearTimeout(moveTimer)
    }
    const timer = window.setTimeout(() => setTypedLen((n) => Math.min(n + 1, introText.length)), 44)
    return () => window.clearTimeout(timer)
  }, [phase, typedLen, introText.length])

  useEffect(() => {
    if (phase !== 'move') return
    const doneTimer = window.setTimeout(() => setPhase('done'), 980)
    return () => window.clearTimeout(doneTimer)
  }, [phase])

  return (
    <main className="heroPage" aria-label="MedRAG landing">
      {phase !== 'done' ? (
        <div className={`heroIntroOverlay phase-${phase}`} aria-hidden="true">
          <div className="heroIntroLine">{introText.slice(0, typedLen)}</div>
        </div>
      ) : null}

      {phase === 'done' ? (
        <section className="heroPanel heroPanelReveal">
          <div className="heroEyebrow">Medical Research Intelligence</div>
          <h1 className="heroTitle">MedRAG Research Assistant</h1>
          <p className="heroSubtitle">
            Search biomedical evidence with multimodal input, hybrid retrieval, and citation-backed summaries in one modern workflow.
          </p>

          <div className="heroFlow" aria-label="How it works">
            <article className="heroStep">
              <div className="heroStepNo">01</div>
              <div className="heroStepTitle">Ask or upload</div>
              <div className="heroStepText">Enter a simple question, upload a document/image, or record voice.</div>
            </article>
            <article className="heroStep">
              <div className="heroStepNo">02</div>
              <div className="heroStepTitle">Retrieve and rank</div>
              <div className="heroStepText">Hybrid retrieval ranks relevant papers using text + embeddings + metadata.</div>
            </article>
            <article className="heroStep">
              <div className="heroStepNo">03</div>
              <div className="heroStepTitle">Review evidence</div>
              <div className="heroStepText">Inspect abstracts, references, and evidence synthesis with filters.</div>
            </article>
          </div>

          <section className="heroPurpose" aria-label="Why MedRAG">
            <div className="heroPurposeHead">Why use MedRAG</div>
            <div className="heroPurposeGrid">
              <article className="heroPurposeCard">
                <div className="heroPurposeTitle">Cut search noise</div>
                <div className="heroPurposeText">Find evidence-backed studies faster without manually scanning large result pages.</div>
              </article>
              <article className="heroPurposeCard">
                <div className="heroPurposeTitle">Stay citation-grounded</div>
                <div className="heroPurposeText">Every result links back to source metadata so your review stays auditable and reliable.</div>
              </article>
              <article className="heroPurposeCard">
                <div className="heroPurposeTitle">Work multimodally</div>
                <div className="heroPurposeText">Start from text, PDF, screenshot, or voice and continue in one consistent research workflow.</div>
              </article>
            </div>
          </section>

          <div className="heroActions">
            <ShimmerButton type="button" label="Open Research Chat" onClick={() => nav('/chat')} />
            <div className="smallMuted">Tip: use simple, focused queries for best retrieval quality.</div>
          </div>
        </section>
      ) : null}
    </main>
  )
}
