import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, RotateCcw, BrainCircuit, Sparkles, Shield, Clock, Layers } from 'lucide-react'

const SUGGESTIONS = [
  '📧 Summarize my unread emails from last week',
  '🎫 What are my open Jira tickets?',
  '📝 Show key decisions from Notion docs',
  '🔍 Find action items across all sources',
]

const SESSION_ID = 'session_' + Math.random().toString(36).slice(2, 9)
const USER_ID    = 'user_demo'

/* ── Source chip ──────────────────────────────────────────── */
function SourceChip({ source }) {
  const type = source?.source?.toLowerCase() || ''
  const cls = type.includes('gmail')  ? 'gmail'
            : type.includes('notion') ? 'notion'
            : type.includes('jira')   ? 'jira'
            : ''
  return (
    <span className={`source-chip ${cls}`}>
      📄 {source.title || source.source_id || source.source || 'Source'}
    </span>
  )
}

/* ── Guardrail badges ─────────────────────────────────────── */
function GuardrailBadges({ flags }) {
  if (!flags) return null
  const items = [
    { label: '🛡 Grounding',  pass: flags.grounding_passed !== false },
    { label: '🔒 Safety',     pass: flags.safety_passed !== false },
    { label: '🕵 No Injection', pass: !flags.injection_detected },
    { label: '🔏 PII Clean',  pass: !flags.pii_redacted },
  ]
  return (
    <div className="guardrail-row">
      {items.map(({ label, pass }) => (
        <span key={label} className={`grail-tag ${pass ? 'pass' : 'warn'}`}>{label}</span>
      ))}
      {typeof flags.grounding_score === 'number' && (
        <span className="grail-tag pass">
          Score {(flags.grounding_score * 100).toFixed(0)}%
        </span>
      )}
    </div>
  )
}

/* ── Single message bubble ────────────────────────────────── */
function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`msg-wrap ${isUser ? 'user' : 'assistant'}`}>
      <div className="msg-header">
        <div className={`msg-avatar ${isUser ? 'user-av' : 'ai-av'}`}>
          {isUser ? 'U' : <BrainCircuit size={14} color="#818cf8" />}
        </div>
        <span className="msg-sender">{isUser ? 'You' : 'Agentic RAG'}</span>
      </div>

      <div className={`msg-bubble ${isUser ? 'user' : 'assistant'} ${msg.blocked ? 'blocked' : ''}`}>
        {msg.blocked && <div style={{ color: 'var(--rose)', marginBottom: 6, fontSize: 12, fontWeight: 600 }}>⛔ Blocked</div>}
        <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>

        {/* Sources */}
        {msg.sources?.length > 0 && (
          <div className="msg-sources">
            {msg.sources.map((s, i) => <SourceChip key={i} source={s} />)}
          </div>
        )}

        {/* Guardrails */}
        {!isUser && msg.guardrail_flags && (
          <GuardrailBadges flags={msg.guardrail_flags} />
        )}
      </div>

      {/* Meta */}
      <div className="msg-meta">
        {msg.latency_ms && (
          <span style={{ display:'flex', alignItems:'center', gap:3 }}>
            <Clock size={10} /> {msg.latency_ms.toFixed(0)}ms
          </span>
        )}
        {msg.iterations > 0 && (
          <span style={{ display:'flex', alignItems:'center', gap:3 }}>
            <Layers size={10} /> {msg.iterations} iteration{msg.iterations !== 1 ? 's' : ''}
          </span>
        )}
      </div>
    </div>
  )
}

/* ── Empty state ──────────────────────────────────────────── */
function EmptyState({ onSuggestion }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Sparkles size={34} color="white" />
      </div>
      <div>
        <div className="empty-title">Ask your AI Knowledge Assistant</div>
        <div className="empty-sub" style={{ marginTop: 8 }}>
          Powered by LangGraph agents with access to your Gmail, Notion & Jira data.
          Every answer is grounded, PII-safe, and injection-protected.
        </div>
      </div>
      <div className="suggestion-chips">
        {SUGGESTIONS.map(s => (
          <button key={s} className="suggestion-chip" onClick={() => onSuggestion(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── Main Chat Page ───────────────────────────────────────── */
export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [toast, setToast]       = useState(null)
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const sendMessage = useCallback(async (text) => {
    const query = (text || input).trim()
    if (!query || loading) return

    const userMsg = { role: 'user', content: query, id: Date.now() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    // Auto-resize textarea back
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: USER_ID,
          session_id: SESSION_ID,
          query,
          include_sources: true,
          max_iterations: 3,
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      const aiMsg = {
        role: 'assistant',
        id: Date.now() + 1,
        content: data.answer,
        sources: data.sources || [],
        guardrail_flags: data.guardrail_flags,
        latency_ms: data.latency_ms,
        iterations: data.iterations,
        blocked: data.is_blocked,
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (err) {
      showToast('Error: ' + err.message, 'error')
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant', id: Date.now() + 1,
          content: '⚠️ Could not reach the backend. Make sure uvicorn is running.',
        },
      ])
    } finally {
      setLoading(false)
    }
  }, [input, loading])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const handleInput = (e) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
  }

  const resetSession = async () => {
    try {
      await fetch('/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID, session_id: SESSION_ID }),
      })
      setMessages([])
      showToast('Session cleared ✓')
    } catch {
      showToast('Reset failed', 'error')
    }
  }

  return (
    <div className="chat-page">
      {/* Top bar */}
      <div className="topbar">
        <div>
          <div className="topbar-title">💬 Chat</div>
          <div className="topbar-sub">Session: {SESSION_ID}</div>
        </div>
        <div className="topbar-right">
          {messages.length > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={resetSession}>
              <RotateCcw size={13} /> Reset
            </button>
          )}
          <span style={{
            display: 'flex', alignItems: 'center', gap: 5,
            fontSize: 12, color: 'var(--text-secondary)',
            background: 'var(--indigo-dim)', padding: '4px 10px',
            borderRadius: 'var(--radius-full)', border: '1px solid var(--border-bright)'
          }}>
            <Shield size={12} color="var(--indigo)" /> Guardrails Active
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 && !loading
          ? <EmptyState onSuggestion={sendMessage} />
          : messages.map(msg => <Message key={msg.id} msg={msg} />)
        }

        {loading && (
          <div className="msg-wrap assistant">
            <div className="msg-header">
              <div className="msg-avatar ai-av"><BrainCircuit size={14} color="#818cf8" /></div>
              <span className="msg-sender">Agentic RAG</span>
            </div>
            <div className="typing-indicator">
              <div className="typing-dot" />
              <div className="typing-dot" />
              <div className="typing-dot" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="chat-input-area">
        <div className="input-box">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            placeholder="Ask anything about your Gmail, Notion, or Jira data…"
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={loading}
          />
          <button
            className="send-btn"
            onClick={() => sendMessage()}
            disabled={!input.trim() || loading}
            aria-label="Send message"
          >
            <Send size={16} color="white" />
          </button>
        </div>
        <div className="input-hint">
          Enter to send · Shift+Enter for new line · Powered by Gemini + LangGraph
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className={`toast ${toast.type}`}>
          {toast.type === 'success' ? '✅' : '❌'} {toast.msg}
        </div>
      )}
    </div>
  )
}
