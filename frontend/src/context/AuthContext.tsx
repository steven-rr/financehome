import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { authApi } from '../api/auth'

interface AuthContextType {
  token: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem('access_token'),
  )

  useEffect(() => {
    if (token) {
      localStorage.setItem('access_token', token)
    } else {
      localStorage.removeItem('access_token')
    }
  }, [token])

  const login = useCallback(async (email: string, password: string) => {
    const data = await authApi.login(email, password)
    setToken(data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    const data = await authApi.register(email, password)
    setToken(data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }, [])

  return (
    <AuthContext.Provider value={{ token, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
