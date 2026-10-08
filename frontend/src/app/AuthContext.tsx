import React, { createContext, useContext, useState, useEffect } from 'react'
import type { CurrentUser } from '../types'
import { getMe } from '../lib/api'

interface AuthContextValue {
  user: CurrentUser | null
  loading: boolean
  error: string | null
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  error: null,
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch((err) => {
        setUser(null)
        // Only set error if it's not a standard 401 unauthenticated
        if (err?.response?.status && err.response.status !== 401) {
          setError('Không thể kết nối đến máy chủ.')
        }
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, error }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext)
}
