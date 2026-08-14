import { useEffect, useState } from 'react'
import {
  Activity, Server, Database, Cpu,
  RefreshCw, CheckCircle, XCircle, Clock
} from 'lucide-react'

const PIPELINE = [
  { icon: '🛡', label: 'Injection\nDetect' },
  { icon: '🔏', label: 'PII\nRedact' },
  { icon: '🔀', label: 'Query\nDecomp' },
  { icon: '🧠', label: 'Planner' },
  { icon: '🔍', label: 'Retriever' },
  { icon: '⚖️', label: 'Evaluator' },
  { icon: '🔄', label: 'Reflector' },
  { icon: '✍️', label: 'Generator' },
  { icon: '✅', label: 'Ground\nCheck' },
  { icon: '🚦', label: 'Safety\nFilter' },
]

export default function DashboardPage() {
  const [health, setHealth]     = useState(null)
  const [loading, setLoading]   = useState(true)
  const [lastRefresh, setLastRefresh] = useState(null)

  const fetchHealth = async () => {
    setLoading(true)
    try {
      const res = await fetch('/health')
      const data = await res.json()
      setHealth(data)
      setLastRefresh(new Date())
    } catch {
      setHealth(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchHealth(); const id = setInterval(fetchHealth, 20000); return () => clearInterval(id) }, [])

  const svcStatus = (name) => health?.services?.[name] ?? 'unknown'

  const StatusIcon = ({ status }) =>
    status === 'healthy'
      ? <CheckCircle size={16} color="var(--emerald)" />
      : <XCircle size={16} color="var(--rose)" />

  const statusBadge = (s) =>
    s === 'healthy' ? 'healthy' : s === 'unknown' ? 'degraded' : 'unhealthy'

  return (
    <div className="chat-page">
      <div className="topbar">
        <div>
          <div className="topbar-title">📊 Dashboard</div>
          <div className="topbar-sub">
            {lastRefresh ? `Last updated ${lastRefresh.toLocaleTimeString()}` : 'Loading…'}
          </div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={fetchHealth} disabled={loading}>
          <RefreshCw size={13} className={loading ? 'spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="page-scroll">
        {/* Stats grid */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon indigo"><Activity size={20} /></div>
            <div>
              <div className="stat-value">{health ? '🟢' : '🔴'}</div>
              <div className="stat-label">API Status</div>
            </div>
            <span className={`stat-badge ${health ? 'healthy' : 'unhealthy'}`}>
              {health ? 'Online' : 'Offline'}
            </span>
          </div>

          <div className="stat-card">
            <div className="stat-icon cyan"><Database size={20} /></div>
            <div>
              <div className="stat-value" style={{ fontSize: 18 }}>
                {svcStatus('qdrant')}
              </div>
              <div className="stat-label">Qdrant Vector DB</div>
            </div>
            <span className={`stat-badge ${statusBadge(svcStatus('qdrant'))}`}>
              {svcStatus('qdrant')}
            </span>
          </div>

          <div className="stat-card">
            <div className="stat-icon emerald"><Server size={20} /></div>
            <div>
              <div className="stat-value" style={{ fontSize: 18 }}>
                {svcStatus('redis')}
              </div>
              <div className="stat-label">Redis Cache</div>
            </div>
            <span className={`stat-badge ${statusBadge(svcStatus('redis'))}`}>
              {svcStatus('redis')}
            </span>
          </div>

          <div className="stat-card">
            <div className="stat-icon purple"><Clock size={20} /></div>
            <div>
              <div className="stat-value">
                {health?.uptime_seconds ? `${Math.floor(health.uptime_seconds / 60)}m` : '—'}
              </div>
              <div className="stat-label">Uptime</div>
            </div>
            <span className="stat-badge healthy">Running</span>
          </div>
        </div>

        {/* Services detail */}
        <div>
          <div className="section-title">🖥 Services</div>
          <div className="info-card">
            {[
              { name: 'FastAPI Backend',  detail: 'http://localhost:8000', svc: 'api' },
              { name: 'Qdrant Vector DB', detail: 'http://localhost:6333', svc: 'qdrant' },
              { name: 'Redis Cache',      detail: 'redis://localhost:6379', svc: 'redis' },
              { name: 'Grafana',          detail: 'http://localhost:3000', svc: 'grafana' },
              { name: 'Prometheus',       detail: 'http://localhost:9090', svc: 'prometheus' },
            ].map(({ name, detail, svc }) => (
              <div key={name} className="service-row">
                <div className="service-name">
                  <StatusIcon status={svc === 'api' ? (health ? 'healthy' : 'unhealthy') : svcStatus(svc)} />
                  {name}
                </div>
                <span className="service-detail">{detail}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Pipeline visualization */}
        <div>
          <div className="section-title">🔄 Agent Pipeline</div>
          <div className="info-card">
            <div className="pipeline-steps">
              {PIPELINE.map((step, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center' }}>
                  <div className="pipeline-step">
                    <div className="step-circle active">
                      <span>{step.icon}</span>
                    </div>
                    <span className="step-label" style={{ whiteSpace: 'pre' }}>
                      {step.label}
                    </span>
                  </div>
                  {i < PIPELINE.length - 1 && (
                    <span className="step-arrow" style={{ marginBottom: 18 }}>›</span>
                  )}
                </div>
              ))}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 12 }}>
              Plan → Retrieve → Evaluate → Reflect (up to 3×) → Generate → Validate
            </div>
          </div>
        </div>

        {/* Config */}
        <div>
          <div className="section-title">⚙️ Configuration</div>
          <div className="info-card">
            {[
              { key: 'LLM Provider', value: 'Gemini 1.5 Flash' },
              { key: 'Embedding Model', value: 'text-embedding-3-small' },
              { key: 'Max Iterations', value: '3' },
              { key: 'PII Threshold', value: '0.85' },
              { key: 'Grounding Strict Mode', value: 'true' },
              { key: 'Mock Connectors', value: 'true' },
            ].map(({ key, value }) => (
              <div key={key} className="service-row">
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{key}</span>
                <span style={{
                  fontSize: 12, fontFamily: 'var(--font-mono)',
                  background: 'var(--indigo-dim)', color: 'var(--indigo-light)',
                  padding: '2px 8px', borderRadius: 'var(--radius-sm)'
                }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
