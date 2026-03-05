import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { authApi } from '../api/auth'

interface MfaPending {
  mfaToken: string
  email: string
}

interface AuthContextType {
  token: string | null
  isDemo: boolean
  isAdmin: boolean
  mfaPending: MfaPending | null
  login: (email: string, password: string) => Promise<boolean>
  completeMfa: (code: string) => Promise<void>
  clearMfaPending: () => void
  register: (email: string, password: string) => Promise<void>
  demoLogin: () => Promise<void>
  githubLogin: (code: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem('access_token'),
  )
  const [isDemo, setIsDemo] = useState<boolean>(() =>
    localStorage.getItem('is_demo') === 'true',
  )
  const [isAdmin, setIsAdmin] = useState<boolean>(false)
  const [mfaPending, setMfaPending] = useState<MfaPending | null>(null)

  useEffect(() => {
    if (token) {
      localStorage.setItem('access_token', token)
      authApi.getMe().then((me) => setIsAdmin(me.is_admin ?? false)).catch(() => setIsAdmin(false))
    } else {
      localStorage.removeItem('access_token')
      setIsAdmin(false)
    }
  }, [token])

  const login = useCallback(async (email: string, password: string): Promise<boolean> => {
    const data = await authApi.login(email, password)
    if (data.mfa_required && data.mfa_token) {
      setMfaPending({ mfaToken: data.mfa_token, email })
      return true // MFA required
    }
    setToken(data.access_token!)
    localStorage.setItem('refresh_token', data.refresh_token!)
    localStorage.setItem('is_demo', 'false')
    setIsDemo(false)
    return false // No MFA
  }, [])

  const completeMfa = useCallback(async (code: string) => {
    if (!mfaPending) throw new Error('No MFA session pending')
    const data = await authApi.mfaVerify(mfaPending.mfaToken, code)
    setToken(data.access_token!)
    localStorage.setItem('refresh_token', data.refresh_token!)
    localStorage.setItem('is_demo', 'false')
    setIsDemo(false)
    setMfaPending(null)
  }, [mfaPending])

  const clearMfaPending = useCallback(() => {
    setMfaPending(null)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    const data = await authApi.register(email, password)
    setToken(data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('is_demo', 'false')
    setIsDemo(false)
  }, [])

  const demoLogin = useCallback(async () => {
    const data = await authApi.demoLogin()
    setToken(data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('is_demo', 'true')
    setIsDemo(true)
  }, [])

  const githubLogin = useCallback(async (code: string) => {
    const data = await authApi.githubCallback(code)
    if (data.mfa_required && data.mfa_token) {
      setMfaPending({ mfaToken: data.mfa_token, email: '' })
      throw new Error('MFA_REQUIRED')
    }
    setToken(data.access_token!)
    localStorage.setItem('refresh_token', data.refresh_token!)
    localStorage.setItem('is_demo', 'false')
    setIsDemo(false)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setIsDemo(false)
    setIsAdmin(false)
    setMfaPending(null)
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('is_demo')
  }, [])

  return (
    <AuthContext.Provider value={{ token, isDemo, isAdmin, mfaPending, login, completeMfa, clearMfaPending, register, demoLogin, githubLogin, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
