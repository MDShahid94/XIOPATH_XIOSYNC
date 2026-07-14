/**
 * XIOPATH — Audit Log Page (Admin)
 * ===================================
 * Chronological event log with filtering and user attribution.
 */
import React, { useState, useEffect } from 'react';
import {
  ScrollText, Search, Filter, RefreshCw, User, Clock,
  Globe, KeyRound, Play, Trash2, Settings, Shield,
  ArrowUpDown, ChevronDown
} from 'lucide-react';

const EVENT_TYPES = {
  auth:      { icon: Shield, color: 'var(--xp-cyan)', label: 'Auth' },
  execute:   { icon: Play, color: 'var(--xp-success)', label: 'Execute' },
  vault:     { icon: KeyRound, color: 'var(--xp-purple)', label: 'Vault' },
  schedule:  { icon: Clock, color: 'var(--xp-warning)', label: 'Schedule' },
  deploy:    { icon: Globe, color: 'var(--xp-info)', label: 'Deploy' },
  admin:     { icon: Settings, color: 'var(--xp-text-muted)', label: 'Admin' },
  delete:    { icon: Trash2, color: 'var(--xp-danger)', label: 'Delete' },
};

export default function AuditPage() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');

  useEffect(() => {
    // Mock audit events
    setTimeout(() => {
      setEvents([
        { id: 1, type: 'auth', action: 'User logged in', user: 'admin', ip: '127.0.0.1', timestamp: new Date(Date.now() - 300000).toISOString() },
        { id: 2, type: 'execute', action: 'Workflow "login_action" dispatched', user: 'client_01', ip: '192.168.1.10', timestamp: new Date(Date.now() - 600000).toISOString(), details: 'Session: xp_abc123, URL: https://mail.google.com' },
        { id: 3, type: 'vault', action: 'Secret "google_password" added', user: 'client_01', ip: '192.168.1.10', timestamp: new Date(Date.now() - 1800000).toISOString() },
        { id: 4, type: 'deploy', action: 'Colab worker deployed', user: 'admin', ip: '127.0.0.1', timestamp: new Date(Date.now() - 3600000).toISOString(), details: 'Profile: lifelonglearnersgroup@gmail.com' },
        { id: 5, type: 'schedule', action: 'Job "Daily Login Check" created', user: 'client_01', ip: '192.168.1.10', timestamp: new Date(Date.now() - 7200000).toISOString(), details: 'Cron: 0 9 * * *' },
        { id: 6, type: 'auth', action: 'User signed up', user: 'client_02', ip: '10.0.0.5', timestamp: new Date(Date.now() - 14400000).toISOString(), details: 'Role: client' },
        { id: 7, type: 'execute', action: 'Workflow "search_products" failed', user: 'client_02', ip: '10.0.0.5', timestamp: new Date(Date.now() - 21600000).toISOString(), details: 'Error: Element not found. Sent to DLQ.' },
        { id: 8, type: 'delete', action: 'Secret "old_api_key" deleted', user: 'admin', ip: '127.0.0.1', timestamp: new Date(Date.now() - 43200000).toISOString() },
        { id: 9, type: 'admin', action: 'Worker heartbeat timeout detected', user: 'system', ip: '—', timestamp: new Date(Date.now() - 86400000).toISOString(), details: 'Worker: worker_colab_03' },
        { id: 10, type: 'vault', action: 'Secret "amazon_password" updated', user: 'client_01', ip: '192.168.1.10', timestamp: new Date(Date.now() - 172800000).toISOString() },
      ]);
      setLoading(false);
    }, 400);
  }, []);

  const filtered = events.filter((e) => {
    if (typeFilter !== 'all' && e.type !== typeFilter) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return e.action.toLowerCase().includes(q) || e.user.toLowerCase().includes(q);
    }
    return true;
  });

  const formatTime = (iso) => {
    const d = new Date(iso);
    const age = Math.floor((Date.now() - d.getTime()) / 60000);
    if (age < 60) return `${age}m ago`;
    if (age < 1440) return `${Math.floor(age / 60)}h ago`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="xp-animate-fade-in">
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Audit Log</h1>
          <p className="xp-page-subtitle">Chronological record of all system events</p>
        </div>
        <button className="xp-btn xp-btn-secondary" onClick={() => { setLoading(true); setTimeout(() => setLoading(false), 400); }}>
          <RefreshCw size={14} className={loading ? 'xp-animate-spin' : ''} />
        </button>
      </div>

      {/* Filters */}
      <div className="xp-card" style={{
        display: 'flex', gap: 'var(--xp-space-3)', alignItems: 'center',
        marginBottom: 'var(--xp-space-5)', padding: 'var(--xp-space-3) var(--xp-space-4)',
      }}>
        <Search size={14} style={{ color: 'var(--xp-text-muted)', flexShrink: 0 }} />
        <input className="xp-input" placeholder="Search events or users..."
          value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}
          style={{ border: 'none', background: 'transparent', padding: '4px 0', flex: 1 }}
        />
        <select className="xp-select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
          style={{ width: '140px' }}>
          <option value="all">All Types</option>
          {Object.entries(EVENT_TYPES).map(([key, cfg]) => (
            <option key={key} value={key}>{cfg.label}</option>
          ))}
        </select>
      </div>

      {/* Timeline */}
      {loading ? (
        <div className="xp-stagger">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="xp-skeleton" style={{ height: '60px', marginBottom: 'var(--xp-space-3)' }} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="xp-card">
          <div className="xp-empty">
            <ScrollText size={40} className="xp-empty-icon" />
            <div className="xp-empty-title">No events found</div>
            <div className="xp-empty-desc">Adjust your filters to see more results.</div>
          </div>
        </div>
      ) : (
        <div style={{ position: 'relative', paddingLeft: '28px' }}>
          {/* Timeline line */}
          <div style={{
            position: 'absolute', left: '11px', top: '12px', bottom: '12px',
            width: '2px', background: 'var(--xp-border-subtle)',
          }} />

          <div className="xp-stagger" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }}>
            {filtered.map((event) => {
              const cfg = EVENT_TYPES[event.type] || EVENT_TYPES.admin;
              const Icon = cfg.icon;
              return (
                <div key={event.id} style={{ position: 'relative' }}>
                  {/* Timeline dot */}
                  <div style={{
                    position: 'absolute', left: '-22px', top: '14px',
                    width: '10px', height: '10px', borderRadius: '50%',
                    background: cfg.color, border: '2px solid var(--xp-bg-base)',
                    boxShadow: `0 0 0 3px ${cfg.color}30`,
                  }} />

                  <div className="xp-card xp-tr-interactive" style={{
                    cursor: 'default',
                    padding: 'var(--xp-space-3) var(--xp-space-4)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)' }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: 'var(--xp-radius-md)',
                        background: `${cfg.color}15`, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', flexShrink: 0,
                      }}>
                        <Icon size={14} style={{ color: cfg.color }} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 'var(--xp-weight-medium)', fontSize: 'var(--xp-text-sm)' }}>
                          {event.action}
                        </div>
                        <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', display: 'flex', gap: 'var(--xp-space-3)' }}>
                          <span><User size={10} style={{ verticalAlign: 'middle' }} /> {event.user}</span>
                          <span>IP: {event.ip}</span>
                          {event.details && (
                            <span style={{ color: 'var(--xp-text-secondary)' }}>{event.details}</span>
                          )}
                        </div>
                      </div>
                      <span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', flexShrink: 0, whiteSpace: 'nowrap' }}>
                        {formatTime(event.timestamp)}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ marginTop: 'var(--xp-space-3)', fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textAlign: 'right' }}>
        Showing {filtered.length} of {events.length} events
      </div>
    </div>
  );
}
