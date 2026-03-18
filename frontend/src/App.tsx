import './App.css'
import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import ChatPage from './pages/ChatPage'
import LandingPage from './pages/LandingPage'
import ResultsPage from './pages/ResultsPage'
import { ChatsProvider } from './state/chats'

export default function App() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const isLanding = location.pathname === '/'

  useEffect(() => {
    function onOpen() {
      setMobileOpen(true)
    }
    window.addEventListener('MedAssist:openSidebar', onOpen as EventListener)
    return () => window.removeEventListener('MedAssist:openSidebar', onOpen as EventListener)
  }, [])

  return (
    <ChatsProvider>
      <div className={isLanding ? "page" : "page shell"}>
        {!isLanding ? <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} /> : null}
        {!isLanding && mobileOpen ? <div className="backdrop mobileOnly" onMouseDown={() => setMobileOpen(false)} /> : null}

        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:chatId" element={<ChatPage />} />
          <Route path="/chat/:chatId/results" element={<ResultsPage />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </div>
    </ChatsProvider>
  )
}



