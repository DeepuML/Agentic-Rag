import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  MessageSquare, LayoutDashboard, Database,
  BrainCircuit, Zap, Circle
} from 'lucide-react'

export default function Layout() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const fetch_ = () =>
      fetch('/health').then(r => r.json()).then(setHealth).catch(() => setHealth(null))
    fetch_()
    const id = setInterval(fetch_, 15000)
    return () => clearInterval(id)
  }, [])

  const svc = (name) => {
    if (!health) return 'yellow'
    return health.services?.[name] === 'healthy' ? 'green' : 'red'
  }

  const navItems = [
    { to: '/chat',      label: 'Chat',       icon: MessageSquare },
    { to: '/dashboard', label: 'Dashboard',  icon: LayoutDashboard },
    { to: '/sources',   label: 'Data Sources', icon: Database },
  ]

  return (
    <div className="app-shell">
      {/* ── Sidebar ─────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">
            <BrainCircuit size={20} color="white" />
          </div>
          <div className="sidebar-logo-text">
            <span className="sidebar-logo-title">Agentic RAG</span>
            <span className="sidebar-logo-sub">Live Knowledge AI</span>
          </div>
        </div>

        <span className="nav-section-label">Navigation</span>

        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <Icon size={17} />
            {label}
          </NavLink>
        ))}

        <div className="sidebar-footer">
          <span className="nav-section-label">Infrastructure</span>
          <div className="status-dots">
            {[
              { label: 'FastAPI',   color: 'green' },
              { label: 'Qdrant',   color: svc('qdrant') },
              { label: 'Redis',    color: svc('redis') },
            ].map(({ label, color }) => (
              <div key={label} className="status-row">
                <span>{label}</span>
                <div className={`dot ${color}`} />
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ── Main content ─────────────────── */}
      <div className="main-panel">
        <Outlet />
      </div>
    </div>
  )
}
