import type { PaperResult } from '../api'

function pct(score: number, maxScore: number): number {
  if (!maxScore || maxScore <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((score / maxScore) * 100)))
}

export default function ArticleModal(props: {
  open: boolean
  onClose: () => void
  paper: PaperResult | null
  maxScore: number
  query: string
}) {
  const p = props.paper
  if (!props.open || !p) return null

  const match = pct(p.score, props.maxScore)
  const pubmedUrl = /^\d+$/.test(p.pmid) ? `https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/` : null

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true" aria-label="Article overview" onMouseDown={props.onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modalTop">
          <div>
            <div className="modalTitle">{p.title}</div>
            <div className="modalSub">
              {p.citation.journal ? <span>{p.citation.journal}</span> : <span>Journal n/a</span>}
              {p.citation.year ? <span>• {p.citation.year}</span> : null}
              <span>• PMID {p.pmid}</span>
            </div>
          </div>
          <button className="iconBtn" type="button" onClick={props.onClose} aria-label="Close overview">
            ✕
          </button>
        </div>

        <div className="matchBox">
          <div className="matchRow">
            <div className="smallMuted">Match to query</div>
            <div className="matchPct">{match}%</div>
          </div>
          <div className="barTrack" aria-hidden="true">
            <div className="barFill" style={{ width: `${match}%` }} />
          </div>
          <div className="smallMuted ellipsis" title={props.query}>
            Query: {props.query}
          </div>
        </div>

        <div className="modalGrid">
          <div className="modalSection">
            <div className="sectionTitle">Abstract</div>
            <div className="para">{p.abstract || 'n/a'}</div>
          </div>

          <div className="modalSection">
            <div className="sectionTitle">Details</div>
            <div className="kv">
              <div className="k">Authors</div>
              <div className="v">{p.citation.authors?.length ? p.citation.authors.join(', ') : 'n/a'}</div>
              <div className="k">MeSH</div>
              <div className="v">{p.mesh_terms?.length ? p.mesh_terms.join(', ') : 'n/a'}</div>
              <div className="k">Keywords</div>
              <div className="v">{p.keywords?.length ? p.keywords.join(', ') : 'n/a'}</div>
              <div className="k">Study type</div>
              <div className="v">{p.publication_types?.length ? p.publication_types.join(', ') : 'n/a'}</div>
              <div className="k">Disease area</div>
              <div className="v">{p.disease_area || 'n/a'}</div>
              <div className="k">Trial stage</div>
              <div className="v">{p.trial_stage || 'n/a'}</div>
            </div>
          </div>

          <div className="modalSection">
            <div className="sectionTitle">Evidence snippets</div>
            {p.evidence?.length ? (
              <div className="snips">
                {p.evidence.slice(0, 4).map((e, idx) => (
                  <div key={idx} className="snip">
                    <div className="snipText">{e.text}</div>
                    <div className="snipWhy">{e.why}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="smallMuted">No snippets returned.</div>
            )}
          </div>
        </div>

        <div className="modalBottom">
          {pubmedUrl ? (
            <a className="btn secondary" href={pubmedUrl} target="_blank" rel="noreferrer">
              Open on PubMed
            </a>
          ) : (
            <div className="smallMuted">No PubMed link available for this ID.</div>
          )}
          <button className="btn" type="button" onClick={props.onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  )
}

