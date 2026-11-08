import { createContext, useContext, useState } from 'react'
import api from './api'

const AuthContext = createContext(null)

function loadUser() {
  try {
    return JSON.parse(localStorage.getItem('user'))
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(loadUser)

  const saveSession = ({ access_token, user }) => {
    localStorage.setItem('token', access_token)
    localStorage.setItem('user', JSON.stringify(user))
    setUser(user)
  }

  const login = async (email, password) => {
    // The login endpoint uses the OAuth2 form format: "username" holds the email
    const form = new URLSearchParams({ username: email, password })
    const { data } = await api.post('/auth/login', form)
    saveSession(data)
  }

  const register = async (name, email, password) => {
    const { data } = await api.post('/auth/register', { name, email, password })
    saveSession(data)
  }

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, login, register, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
