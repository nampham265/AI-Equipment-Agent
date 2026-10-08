import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './app/AuthContext'
import { Navbar } from './components/Navbar'
import { LoginPage } from './features/auth/LoginPage'
import { ChatPage } from './features/chat/ChatPage'
import { MyRequestsPage } from './features/requests/MyRequestsPage'
import { ManagerDashboard } from './features/manager/ManagerDashboard'
import { AdminDashboard } from './features/admin/AdminDashboard'

function AppLayout() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <div className="loading">Đang tải...</div>
      </div>
    )
  }

  if (!user) {
    return <LoginPage />
  }

  return (
    <div className="layout">
      <Navbar />
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/my-requests" element={<MyRequestsPage />} />
        <Route
          path="/manager"
          element={
            user.is_manager
              ? <ManagerDashboard />
              : <Navigate to="/" replace />
          }
        />
        <Route
          path="/admin"
          element={
            user.is_admin
              ? <AdminDashboard />
              : <Navigate to="/" replace />
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppLayout />
      </AuthProvider>
    </BrowserRouter>
  )
}
