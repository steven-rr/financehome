import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuth } from './context/AuthContext'
import Accounts from './pages/Accounts'
import Analytics from './pages/Analytics'
import Dashboard from './pages/Dashboard'
import Insights from './pages/Insights'
import Login from './pages/Login'
import Reports from './pages/Reports'
import OAuthCallback from './pages/OAuthCallback'
import Subscriptions from './pages/Subscriptions'
import Transactions from './pages/Transactions'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/oauth-callback" element={<ProtectedRoute><OAuthCallback /></ProtectedRoute>} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="accounts" element={<Accounts />} />
        <Route path="transactions" element={<Transactions />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="subscriptions" element={<Subscriptions />} />
        <Route path="insights" element={<Insights />} />
        <Route path="reports" element={<Reports />} />
      </Route>
    </Routes>
  )
}
