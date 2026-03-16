import { useEffect } from 'react'

export default function Modal(props: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') props.onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [props])

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true" onMouseDown={props.onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modalTop">
          <div className="modalTitle">{props.title}</div>
          <button className="iconBtn" onClick={props.onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modalBody">{props.children}</div>
      </div>
    </div>
  )
}
