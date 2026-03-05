import { CreditCard } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function GitHubCallback() {
  const [searchParams] = useSearchParams()
  const { githubLogin } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  useEffect(() => {
    const code = searchParams.get('code')
    if (!code) {
      setError('No authorization code received from GitHub.')
      return
    }

    githubLogin(code)
      .then(() => navigate('/', { replace: true }))
      .catch((err) => {
        if (err instanceof Error && err.message === 'MFA_REQUIRED') {
          navigate('/login', { replace: true })
        } else {
          setError('Failed to sign in with GitHub. Please try again.')
        }
      })
  }, [searchParams, githubLogin, navigate])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
        <div className="text-center">
          <CreditCard className="w-10 h-10 text-emerald-600 mx-auto mb-4" />
          <p className="text-red-600 dark:text-red-400 mb-4">{error}</p>
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors"
          >
            Back to Login
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
      <div className="text-center">
        <CreditCard className="w-10 h-10 text-emerald-600 mx-auto mb-4" />
        <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-slate-600 dark:text-slate-400 text-sm">Signing in with GitHub...</p>
      </div>
    </div>
  )
}
