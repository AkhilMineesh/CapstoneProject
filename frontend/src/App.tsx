import './App.css'
import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import ChatPage from './pages/ChatPage'
import ResultsPage from './pages/ResultsPage'
import { ChatsProvider } from './state/chats'

export default function App() {
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    function onOpen() {
      setMobileOpen(true)
    }
    window.addEventListener('medrag:openSidebar', onOpen as EventListener)
    return () => window.removeEventListener('medrag:openSidebar', onOpen as EventListener)
  }, [])

  return (
    <ChatsProvider>
      <div className="page shell">
        <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
        {mobileOpen ? <div className="backdrop mobileOnly" onMouseDown={() => setMobileOpen(false)} /> : null}

        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/chat/:chatId" element={<ChatPage />} />
          <Route path="/chat/:chatId/results" element={<ResultsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </ChatsProvider>
  )
}

