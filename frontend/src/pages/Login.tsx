import { ArrowLeft, CreditCard, Github, Play, Shield } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuth } from '../context/AuthContext'

function MFAVerifyForm({
  onSubmit,
  onBack,
  error,
  loading,
}: {
  onSubmit: (code: string) => Promise<void>
  onBack: () => void
  error: string
  loading: boolean
}) {
  const [code, setCode] = useState('')
  const [useRecovery, setUseRecovery] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onSubmit(code)
  }

  return (
    <>
      <div className="flex items-center gap-2 mb-2">
        <Shield className="w-5 h-5 text-emerald-600" />
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
          Two-Factor Authentication
        </h2>
      </div>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
        {useRecovery
          ? 'Enter one of your recovery codes'
          : 'Enter the 6-digit code from your authenticator app'}
      </p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            autoFocus
            maxLength={useRecovery ? 9 : 6}
            inputMode={useRecovery ? 'text' : 'numeric'}
            autoComplete="one-time-code"
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 text-center text-lg tracking-widest"
            placeholder={useRecovery ? 'xxxx-xxxx' : '000000'}
          />
        </div>

        <button
          type="submit"
          disabled={loading || !code}
          className="w-full py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
        >
          {loading ? 'Verifying...' : 'Verify'}
        </button>
      </form>

      <div className="mt-4 flex items-center justify-between">
        <button
          onClick={onBack}
          className="text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 flex items-center gap-1"
        >
          <ArrowLeft className="w-3 h-3" />
          Back
        </button>
        <button
          onClick={() => { setUseRecovery(!useRecovery); setCode('') }}
          className="text-sm text-emerald-600 hover:underline"
        >
          {useRecovery ? 'Use authenticator code' : 'Use a recovery code'}
        </button>
      </div>
    </>
  )
}

const PASSWORD_RULES = [
  { label: 'At least 8 characters', test: (p: string) => p.length >= 8 },
  { label: 'One uppercase letter', test: (p: string) => /[A-Z]/.test(p) },
  { label: 'One lowercase letter', test: (p: string) => /[a-z]/.test(p) },
  { label: 'One number', test: (p: string) => /\d/.test(p) },
  { label: 'One special character', test: (p: string) => /[^A-Za-z0-9]/.test(p) },
]

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isRegister, setIsRegister] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [demoLoading, setDemoLoading] = useState(false)
  const [githubLoading, setGithubLoading] = useState(false)
  const { login, register, demoLogin, mfaPending, completeMfa, clearMfaPending } = useAuth()
  const navigate = useNavigate()

  const passwordValid = PASSWORD_RULES.every((r) => r.test(password))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (isRegister && !passwordValid) {
      setError('Please meet all password requirements')
      return
    }
    setLoading(true)
    try {
      if (isRegister) {
        await register(email, password)
        navigate('/')
      } else {
        const mfaRequired = await login(email, password)
        if (!mfaRequired) navigate('/')
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleMfaSubmit = async (code: string) => {
    setError('')
    setLoading(true)
    try {
      await completeMfa(code)
      navigate('/')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Invalid code'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleMfaBack = () => {
    clearMfaPending()
    setError('')
  }

  const handleGitHubLogin = async () => {
    setError('')
    setGithubLoading(true)
    try {
      const { url } = await authApi.githubAuthorize()
      window.location.href = url
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      setError(message)
      setGithubLoading(false)
    }
  }

  const handleDemoLogin = async () => {
    setError('')
    setDemoLoading(true)
    try {
      await demoLogin()
      navigate('/')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      setError(message)
    } finally {
      setDemoLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-2">
            <CreditCard className="w-8 h-8 text-emerald-600" />
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">FinanceHome</h1>
          </div>
          <p className="text-slate-500 dark:text-slate-400">Your personal finance dashboard</p>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-8">
          {mfaPending ? (
            <MFAVerifyForm
              onSubmit={handleMfaSubmit}
              onBack={handleMfaBack}
              error={error}
              loading={loading}
            />
          ) : (
            <>
              <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 mb-6">
                {isRegister ? 'Create Account' : 'Sign In'}
              </h2>

              {error && (
                <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                    placeholder="you@example.com"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={isRegister ? 8 : 1}
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                    placeholder="••••••••"
                  />
                  {isRegister && password.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {PASSWORD_RULES.map((rule) => (
                        <li key={rule.label} className={`text-xs flex items-center gap-1.5 ${rule.test(password) ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-500'}`}>
                          <span>{rule.test(password) ? '\u2713' : '\u2022'}</span>
                          {rule.label}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
                >
                  {loading ? 'Loading...' : isRegister ? 'Create Account' : 'Sign In'}
                </button>
              </form>

              <p className="mt-4 text-center text-sm text-slate-500 dark:text-slate-400">
                {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
                <button
                  onClick={() => setIsRegister(!isRegister)}
                  className="text-emerald-600 font-medium hover:underline"
                >
                  {isRegister ? 'Sign In' : 'Create one'}
                </button>
              </p>

              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-200 dark:border-slate-700" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white dark:bg-slate-900 text-slate-400">or</span>
                </div>
              </div>

              <button
                onClick={handleGitHubLogin}
                disabled={githubLoading}
                className="w-full py-2.5 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-lg text-sm font-medium hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <Github className="w-4 h-4" />
                {githubLoading ? 'Redirecting...' : 'Continue with GitHub'}
              </button>

              <div className="my-4" />

              <button
                onClick={handleDemoLogin}
                disabled={demoLoading}
                className="w-full py-2.5 border-2 border-emerald-600 text-emerald-700 dark:text-emerald-400 rounded-lg text-sm font-medium hover:bg-emerald-50 dark:hover:bg-emerald-900/30 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <Play className="w-4 h-4" />
                {demoLoading ? 'Setting up demo...' : 'Try Demo — No Sign Up Required'}
              </button>
              <p className="mt-2 text-center text-xs text-slate-400 dark:text-slate-400">
                Explore with sample data from a fictional budget
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
