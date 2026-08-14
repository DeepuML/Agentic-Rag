import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { BrainCircuit, Eye, EyeOff, User, Lock, Mail, ArrowRight, Sparkles } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const PARTICLE_COUNT = 18

export default function LoginPage() {
  const navigate   = useNavigate()
  const { login, register } = useAuth()

  const [tab,     setTab]     = useState('login')   // 'login' | 'register'
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const [showPw,  setShowPw]  = useState(false)

  // Fields
  const [username,    setUsername]    = useState('')
  const [displayName, setDisplayName] = useState('')
  const [email,       setEmail]       = useState('')
  const [password,    setPassword]    = useState('')

  const reset = () => { setError(''); setUsername(''); setDisplayName(''); setEmail(''); setPassword('') }

  const switchTab = (t) => { setTab(t); reset() }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    await new Promise(r => setTimeout(r, 600)) // slight UX delay

    let result
    if (tab === 'login') {
      result = login(username.trim(), password)
    } else {
      result = register(username.trim(), displayName.trim(), email.trim(), password)
    }

    setLoading(false)
    if (!result.ok) { setError(result.error); return }
    navigate('/chat')
  }

  return (
    <div className="auth-page">
      {/* Animated background orbs */}
      <div className="auth-orb auth-orb-1" />
      <div className="auth-orb auth-orb-2" />
      <div className="auth-orb auth-orb-3" />

      {/* Floating particles */}
      {Array.from({ length: PARTICLE_COUNT }).map((_, i) => (
        <div key={i} className="auth-particle" style={{
          left: `${Math.random() * 100}%`,
          top:  `${Math.random() * 100}%`,
          animationDelay: `${Math.random() * 6}s`,
          animationDuration: `${4 + Math.random() * 6}s`,
        }} />
      ))}

      {/* Card */}
      <div className="auth-card">
        {/* Logo */}
        <div className="auth-logo">
          <div className="auth-logo-icon">
            <BrainCircuit size={28} color="white" />
          </div>
          <div>
            <div className="auth-logo-title">Agentic RAG</div>
            <div className="auth-logo-sub">Live Knowledge Assistant</div>
          </div>
        </div>

        {/* Tabs */}
        <div className="auth-tabs">
          <button
            className={`auth-tab ${tab === 'login' ? 'active' : ''}`}
            onClick={() => switchTab('login')}
          >
            Sign In
          </button>
          <button
            className={`auth-tab ${tab === 'register' ? 'active' : ''}`}
            onClick={() => switchTab('register')}
          >
            Create Account
          </button>
          <div className={`auth-tab-indicator ${tab === 'register' ? 'right' : ''}`} />
        </div>

        {/* Headline */}
        <div className="auth-headline">
          {tab === 'login'
            ? <>Welcome back <span className="auth-sparkle"><Sparkles size={16}/></span></>
            : <>Get started today <span className="auth-sparkle"><Sparkles size={16}/></span></>
          }
        </div>
        <div className="auth-sub">
          {tab === 'login'
            ? 'Sign in to your AI knowledge workspace'
            : 'Create your account and start querying your data'
          }
        </div>

        {/* Error */}
        {error && (
          <div className="auth-error">
            <span>⚠️</span> {error}
          </div>
        )}

        {/* Form */}
        <form className="auth-form" onSubmit={handleSubmit}>
          {/* Display name (register only) */}
          {tab === 'register' && (
            <div className="auth-field">
              <label className="auth-label">Full Name</label>
              <div className="auth-input-wrap">
                <User size={16} className="auth-input-icon" />
                <input
                  className="auth-input"
                  type="text"
                  placeholder="John Doe"
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  required
                  autoFocus
                />
              </div>
            </div>
          )}

          {/* Email (register only) */}
          {tab === 'register' && (
            <div className="auth-field">
              <label className="auth-label">Email</label>
              <div className="auth-input-wrap">
                <Mail size={16} className="auth-input-icon" />
                <input
                  className="auth-input"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Username */}
          <div className="auth-field">
            <label className="auth-label">Username</label>
            <div className="auth-input-wrap">
              <span className="auth-input-prefix">@</span>
              <input
                className="auth-input auth-input-prefixed"
                type="text"
                placeholder="your_username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                autoFocus={tab === 'login'}
                autoComplete="username"
              />
            </div>
          </div>

          {/* Password */}
          <div className="auth-field">
            <label className="auth-label">
              Password
              {tab === 'login' && (
                <span className="auth-forgot">Forgot?</span>
              )}
            </label>
            <div className="auth-input-wrap">
              <Lock size={16} className="auth-input-icon" />
              <input
                className="auth-input"
                type={showPw ? 'text' : 'password'}
                placeholder={tab === 'login' ? '••••••••' : 'Min. 6 characters'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
              />
              <button
                type="button"
                className="auth-pw-toggle"
                onClick={() => setShowPw(p => !p)}
                tabIndex={-1}
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {/* Submit */}
          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? (
              <span className="auth-spinner" />
            ) : (
              <>
                {tab === 'login' ? 'Sign In' : 'Create Account'}
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        {/* Footer switch */}
        <div className="auth-footer">
          {tab === 'login' ? (
            <>Don't have an account?{' '}
              <button className="auth-link" onClick={() => switchTab('register')}>Sign up free</button>
            </>
          ) : (
            <>Already have an account?{' '}
              <button className="auth-link" onClick={() => switchTab('login')}>Sign in</button>
            </>
          )}
        </div>

        {/* Demo hint */}
        <div className="auth-demo-hint">
          <span>✨ Demo:</span> Register any username + password to get started instantly
        </div>
      </div>
    </div>
  )
}
