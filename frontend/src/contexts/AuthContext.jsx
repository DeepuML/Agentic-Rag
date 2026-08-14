import { createContext, useContext, useState, useCallback } from 'react'

const AuthContext = createContext(null)

const STORAGE_KEY = 'rag_auth_user'
const USERS_KEY   = 'rag_auth_users'

/* ── Helpers ─────────────────────────────────────────────── */
const hashPass = (p) => btoa(encodeURIComponent(p + '::rag_salt'))

function loadUser() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) } catch { return null }
}

function loadUsers() {
  try { return JSON.parse(localStorage.getItem(USERS_KEY)) || {} } catch { return {} }
}

function saveUsers(users) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users))
}

function avatarColor(name) {
  const colors = [
    ['#6366f1','#818cf8'], ['#06b6d4','#22d3ee'], ['#a855f7','#c084fc'],
    ['#10b981','#34d399'], ['#f59e0b','#fbbf24'], ['#f43f5e','#fb7185'],
  ]
  const idx = (name?.charCodeAt(0) || 0) % colors.length
  return colors[idx]
}

/* ── Provider ─────────────────────────────────────────────── */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(loadUser)

  const login = useCallback((username, password) => {
    const users = loadUsers()
    const stored = users[username.toLowerCase()]
    if (!stored) return { ok: false, error: 'Account not found. Please register first.' }
    if (stored.hash !== hashPass(password)) return { ok: false, error: 'Incorrect password.' }
    const u = { username, displayName: stored.displayName, email: stored.email, createdAt: stored.createdAt }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(u))
    setUser(u)
    return { ok: true }
  }, [])

  const register = useCallback((username, displayName, email, password) => {
    if (!username.trim() || !displayName.trim() || !password.trim())
      return { ok: false, error: 'All fields are required.' }
    if (username.length < 3)
      return { ok: false, error: 'Username must be at least 3 characters.' }
    if (password.length < 6)
      return { ok: false, error: 'Password must be at least 6 characters.' }
    if (!/^[a-zA-Z0-9_-]+$/.test(username))
      return { ok: false, error: 'Username can only contain letters, numbers, _ and -.' }

    const users = loadUsers()
    if (users[username.toLowerCase()])
      return { ok: false, error: 'Username already taken.' }

    users[username.toLowerCase()] = {
      displayName, email, hash: hashPass(password),
      createdAt: new Date().toISOString(),
    }
    saveUsers(users)

    const u = { username, displayName, email, createdAt: users[username.toLowerCase()].createdAt }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(u))
    setUser(u)
    return { ok: true }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setUser(null)
  }, [])

  // Derived helpers
  const initials = user
    ? user.displayName.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
    : '?'
  const [fromColor, toColor] = user ? avatarColor(user.username) : ['#6366f1','#818cf8']
  const avatarGradient = `linear-gradient(135deg, ${fromColor} 0%, ${toColor} 100%)`

  // user_id safe for backend (alphanumeric + _-)
  const userId = user?.username.replace(/[^a-zA-Z0-9_-]/g, '_') || 'anonymous'

  return (
    <AuthContext.Provider value={{ user, login, register, logout, initials, avatarGradient, userId }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
