import { useState } from 'react'
import { Zap, RefreshCw, Mail, FileText, Ticket } from 'lucide-react'

const CONNECTORS = [
  {
    key: 'gmail',
    icon: '📧',
    title: 'Gmail',
    sub: 'Email inbox connector',
    color: '#ea4335',
    bg: 'rgba(234,67,53,0.08)',
    border: 'rgba(234,67,53,0.2)',
    description: 'Fetches emails from your inbox via Gmail OAuth2. Extracts text, sender, subject, and timestamps for RAG indexing.',
    fields: ['GMAIL_CLIENT_ID', 'GMAIL_CLIENT_SECRET', 'GMAIL_REFRESH_TOKEN'],
  },
  {
    key: 'notion',
    icon: '📝',
    title: 'Notion',
    sub: 'Workspace connector',
    color: '#ccc',
    bg: 'rgba(255,255,255,0.04)',
    border: 'rgba(255,255,255,0.1)',
    description: 'Syncs pages from your Notion workspace database. Supports rich text, titles, and nested blocks.',
    fields: ['NOTION_API_TOKEN', 'NOTION_DATABASE_ID'],
  },
  {
    key: 'jira',
    icon: '🎫',
    title: 'Jira',
    sub: 'Issue tracker connector',
    color: '#4d9de0',
    bg: 'rgba(0,82,204,0.08)',
    border: 'rgba(0,82,204,0.2)',
    description: 'Pulls issues from your Jira project using REST API. Includes summaries, descriptions, statuses, and assignees.',
    fields: ['JIRA_SERVER_URL', 'JIRA_EMAIL', 'JIRA_API_TOKEN'],
  },
]

export default function SourcesPage() {
  const [running, setRunning]   = useState(null)
  const [result, setResult]     = useState(null)
  const [toast, setToast]       = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 4000)
  }

  const triggerIngest = async (connectors) => {
    setRunning(connectors.join(','))
    setResult(null)
    try {
      const res = await fetch('/ingest/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connectors }),
      })
      const data = await res.json()
      setResult(data)
      showToast(`✓ Ingestion complete for: ${connectors.join(', ')}`)
    } catch (e) {
      showToast('Ingestion failed: ' + e.message, 'error')
    } finally {
      setRunning(null)
    }
  }

  return (
    <div className="chat-page">
      <div className="topbar">
        <div>
          <div className="topbar-title">🔌 Data Sources</div>
          <div className="topbar-sub">Configure and trigger data ingestion connectors</div>
        </div>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => triggerIngest(['gmail', 'notion', 'jira'])}
          disabled={!!running}
        >
          {running ? <RefreshCw size={13} className="spin" /> : <Zap size={13} />}
          {running ? 'Ingesting…' : 'Ingest All'}
        </button>
      </div>

      <div className="page-scroll">
        {/* Connector cards */}
        <div>
          <div className="section-title">🔌 Connectors</div>
          <div className="connector-grid">
            {CONNECTORS.map(c => (
              <div key={c.key} className="connector-card" style={{ borderColor: running === c.key ? c.color : undefined }}>
                <div className="connector-header">
                  <div
                    className="connector-icon"
                    style={{ background: c.bg, border: `1px solid ${c.border}` }}
                  >
                    {c.icon}
                  </div>
                  <div>
                    <div className="connector-title">{c.title}</div>
                    <div className="connector-sub">{c.sub}</div>
                  </div>
                </div>

                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  {c.description}
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2, fontWeight: 600, letterSpacing: '0.05em' }}>
                    ENV VARS
                  </div>
                  {c.fields.map(f => (
                    <code key={f} style={{
                      fontSize: 11, fontFamily: 'var(--font-mono)',
                      background: 'var(--bg-base)', color: 'var(--cyan)',
                      padding: '2px 8px', borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border)'
                    }}>{f}</code>
                  ))}
                </div>

                <div style={{ display: 'flex', gap: 8 }}>
                  <span style={{
                    padding: '3px 10px', borderRadius: 'var(--radius-full)',
                    background: 'rgba(245,158,11,0.1)', color: 'var(--amber)',
                    fontSize: 11, fontWeight: 600
                  }}>
                    Mock Mode
                  </span>
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ marginLeft: 'auto' }}
                    onClick={() => triggerIngest([c.key])}
                    disabled={!!running}
                  >
                    {running === c.key
                      ? <><RefreshCw size={12} className="spin" /> Running…</>
                      : <><Zap size={12} /> Trigger</>
                    }
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Ingestion result */}
        {result && (
          <div>
            <div className="section-title">📋 Last Ingestion Result</div>
            <div className="info-card">
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 12 }}>
                {result.message}
              </div>
              {result.summary && Object.entries(result.summary).map(([k, v]) => (
                <div key={k} className="service-row">
                  <span style={{ fontSize: 13 }}>{k}</span>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 12,
                    color: 'var(--emerald)',
                    background: 'rgba(16,185,129,0.08)',
                    padding: '2px 8px', borderRadius: 'var(--radius-sm)'
                  }}>
                    {JSON.stringify(v)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* How it works */}
        <div>
          <div className="section-title">⚙️ How Ingestion Works</div>
          <div className="info-card">
            {[
              { step: '1', text: 'Connector fetches raw documents from the data source (or mock data)' },
              { step: '2', text: 'Documents are chunked into overlapping segments (~512 tokens each)' },
              { step: '3', text: 'Each chunk is embedded using text-embedding-3-small' },
              { step: '4', text: 'Embeddings are upserted into Qdrant with metadata (source, id, timestamp)' },
              { step: '5', text: 'The pipeline polls every 60s — or trigger manually above' },
            ].map(({ step, text }) => (
              <div key={step} className="service-row">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 24, height: 24, borderRadius: '50%',
                    background: 'var(--indigo-dim)', border: '1px solid var(--border-bright)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, fontWeight: 700, color: 'var(--indigo-light)', flexShrink: 0
                  }}>
                    {step}
                  </div>
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{text}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {toast && (
        <div className={`toast ${toast.type}`}>
          {toast.type === 'success' ? '✅' : '❌'} {toast.msg}
        </div>
      )}
    </div>
  )
}
