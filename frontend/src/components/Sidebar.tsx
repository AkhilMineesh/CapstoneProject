import { useMemo } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useChats } from '../state/chats'

function formatTime(ts: number): string {
  try {
    const d = new Date(ts)
    return d.toLocaleString(undefined, { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

export default function Sidebar(props: { mobileOpen: boolean; setMobileOpen: (v: boolean) => void }) {
  const { chats, clearChats, deleteChat, activeChatId, setActiveChatId } = useChats()
  const navigate = useNavigate()
  const items = useMemo(() => chats, [chats])

  return (
    <aside className={props.mobileOpen ? 'sidebar open' : 'sidebar'} aria-label="Chat history">
      <div className="sideTop">
        <div className="sideBrand" role="button" tabIndex={0} onClick={() => navigate('/')}>
          <div className="logo" aria-hidden="true">
            <img src="/medrag-logo.svg" alt="" />
          </div>
          <div className="brandText">
            <div className="brandTitle">MedRAG</div>
            <div className="brandSub">Evidence workspace</div>
          </div>
        </div>
        <button
          className="iconBtn mobileOnly"
          onClick={() => props.setMobileOpen(false)}
          aria-label="Close sidebar"
          type="button"
        >
          X
        </button>
      </div>

      <div className="sideActions">
        <button className="btn secondary" type="button" onClick={() => navigate('/')}>
          New chat
        </button>
        <button
          className="btn ghost"
          type="button"
          onClick={() => {
            clearChats()
            navigate('/')
          }}
          disabled={!items.length}
        >
          Clear history
        </button>
      </div>

      <div className="chatList" role="list">
        {items.length ? (
          items.map((c) => (
            <div key={c.id} className="chatRow" role="listitem">
              <NavLink
                className={({ isActive }) => (isActive ? 'chatItem active' : 'chatItem')}
                to={`/chat/${c.id}`}
                onClick={() => {
                  setActiveChatId(c.id)
                  props.setMobileOpen(false)
                }}
              >
                <div className="chatTitle">{c.title}</div>
                <div className="chatMeta">{formatTime(c.updatedAt)}</div>
              </NavLink>
              <button
                className="iconBtn"
                type="button"
                aria-label={`Delete chat ${c.title}`}
                onClick={() => {
                  deleteChat(c.id)
                  if (activeChatId === c.id) navigate('/')
                }}
              >
                🗑
              </button>
            </div>
          ))
        ) : (
          <div className="emptySide">
            <div className="smallMuted">No chats yet.</div>
            <div className="smallMuted">Start a prompt to create your first workspace.</div>
          </div>
        )}
      </div>

      <div className="sideFooter">
        <div className="smallMuted">Abstract-level analysis only. Not a clinical decision tool.</div>
      </div>
    </aside>
  )
}
