import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { authApi } from '../api/auth'

interface AuthContextType {
  token: string | null
  isDemo: boolean
  isAdmin: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  demoLogin: () => Promise<void>
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

  useEffect(() => {
    if (token) {
      localStorage.setItem('access_token', token)
      authApi.getMe().then((me) => setIsAdmin(me.is_admin ?? false)).catch(() => setIsAdmin(false))
    } else {
      localStorage.removeItem('access_token')
      setIsAdmin(false)
    }
  }, [token])

  const login = useCallback(async (email: string, password: string) => {
    const data = await authApi.login(email, password)
    setToken(data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('is_demo', 'false')
    setIsDemo(false)
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

  const logout = useCallback(() => {
    setToken(null)
    setIsDemo(false)
    setIsAdmin(false)
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('is_demo')
  }, [])

  return (
    <AuthContext.Provider value={{ token, isDemo, isAdmin, login, register, demoLogin, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
