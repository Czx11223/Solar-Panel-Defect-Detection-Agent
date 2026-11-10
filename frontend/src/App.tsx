import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'

import AppLayout from './components/AppLayout'
import ProtectedRoute from './components/ProtectedRoute'
import DetectPage from './pages/Detect'
import HistoryPage from './pages/History'
import LoginPage from './pages/Login'
import RegisterPage from './pages/Register'
import ChatPage from './pages/Chat'

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<DetectPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/chat" element={<ChatPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  )
}
