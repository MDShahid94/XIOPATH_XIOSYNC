/**
 * XIOPATH — Session History Page
 * ================================
 * Browse, filter, and inspect past workflow executions.
 * Provides status filtering, time sorting, and re-run capabilities.
 */
import React, { useState, useEffect, useMemo } from 'react';
import {
  History, Search, Filter, RefreshCw, Loader2, Clock,
  CheckCircle, XCircle, Activity, ChevronDown, PlayCircle,
  Globe, Calendar, ArrowUpDown, ExternalLink
} from 'lucide-react';
import api from '../../lib/api';
import { workflowsAPI } from '../../lib/api-v2';
import useToastStore from '../../stores/toastStore';

const STATUS_BADGES = {
  completed: { class: 'xp-badge-success', label: 'Completed', Icon: CheckCircle },
  failed:    { class: 'xp-badge-danger',  label: 'Failed',    Icon: XCircle },
  running:   { class: 'xp-badge-cyan',    label: 'Running',   Icon: Activity },
  queued:    { class: 'xp-badge-warning',  label: 'Queued',    Icon: Clock },
};

export default function SessionsPage() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('desc');
  const [expandedId, setExpandedId] = useState(null);

  const addToast = useToastStore((s) => s.addToast);

  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const res = await api.get('/sessions');
      setSessions(res.data.sessions || []);
    } catch {
      setSessions([]);
    }
    setLoading(false);
  };

  const filtered = useMemo(() => {
    let result = [...sessions];
    if (statusFilter !== 'all') {
      result = result.filter((s) => s.status === statusFilter);
    }
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      result = result.filter((s) =>
        s.intent?.toLowerCase().includes(q) ||
        s.url?.toLowerCase().includes(q) ||
        s.id?.toLowerCase().includes(q)
      );
    }
    result.sort((a, b) => {
      const diff = new Date(a.started_at) - new Date(b.started_at);
      return sortOrder === 'desc' ? -diff : diff;
    });
    return result;
  }, [sessions, statusFilter, searchTerm, sortOrder]);

  const formatTime = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
           d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="xp-animate-fade-in">
      {/* ─── Page Header ──────────────────────────── */}
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Sessions</h1>
          <p className="xp-page-subtitle">Browse and inspect workflow execution history</p>
        </div>
        <button className="xp-btn xp-btn-secondary" onClick={fetchSessions} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'xp-animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* ─── Filters Bar ──────────────────────────── */}
      <div className="xp-card" style={{
        display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)',
        marginBottom: 'var(--xp-space-5)', padding: 'var(--xp-space-3) var(--xp-space-4)',
      }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <Search size={14} style={{
            position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)',
            color: 'var(--xp-text-muted)',
          }} />
          <input
            className="xp-input"
            placeholder="Search by intent, URL, or session ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ paddingLeft: '36px' }}
          />
        </div>

        <select className="xp-select" value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ width: '160px' }}
        >
          <option value="all">All Statuses</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
          <option value="queued">Queued</option>
        </select>

        <button className="xp-btn xp-btn-ghost"
          onClick={() => setSortOrder((o) => o === 'desc' ? 'asc' : 'desc')}
          data-tooltip={sortOrder === 'desc' ? 'Newest first' : 'Oldest first'}
        >
          <ArrowUpDown size={16} />
        </button>
      </div>

      {/* ─── Sessions Table ───────────────────────── */}
      {loading ? (
        <div className="xp-card">
          <div className="xp-stagger">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="xp-skeleton" style={{ height: '52px', marginBottom: 'var(--xp-space-3)' }} />
            ))}
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="xp-card">
          <div className="xp-empty">
            <History size={40} className="xp-empty-icon" />
            <div className="xp-empty-title">No sessions found</div>
            <div className="xp-empty-desc">
              {searchTerm || statusFilter !== 'all'
                ? 'Try adjusting your filters.'
                : 'Execute a workflow to see sessions here.'}
            </div>
          </div>
        </div>
      ) : (
        <div className="xp-card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="xp-table">
            <thead>
              <tr>
                <th className="xp-th">Session ID</th>
                <th className="xp-th">Intent</th>
                <th className="xp-th">URL</th>
                <th className="xp-th">Status</th>
                <th className="xp-th">Steps</th>
                <th className="xp-th">Duration</th>
                <th className="xp-th">Started</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const badge = STATUS_BADGES[s.status] || STATUS_BADGES.queued;
                const Icon = badge.Icon;
                const isExpanded = expandedId === s.id;
                return (
                  <React.Fragment key={s.id}>
                    <tr className="xp-tr-interactive"
                      onClick={() => setExpandedId(isExpanded ? null : s.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="xp-td">
                        <span className="xp-mono" style={{ fontSize: 'var(--xp-text-xs)' }}>{s.id}</span>
                      </td>
                      <td className="xp-td" style={{ fontWeight: 'var(--xp-weight-medium)' }}>{s.intent}</td>
                      <td className="xp-td">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          <Globe size={12} style={{ color: 'var(--xp-text-muted)', flexShrink: 0 }} />
                          <span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {s.url?.replace('https://', '')}
                          </span>
                        </div>
                      </td>
                      <td className="xp-td">
                        <span className={`xp-badge ${badge.class}`}>
                          <Icon size={10} /> {badge.label}
                        </span>
                      </td>
                      <td className="xp-td" style={{ fontFamily: 'var(--xp-font-mono)', fontSize: 'var(--xp-text-xs)' }}>
                        {s.steps || '—'}
                      </td>
                      <td className="xp-td" style={{ fontFamily: 'var(--xp-font-mono)', fontSize: 'var(--xp-text-xs)' }}>
                        {s.duration || '—'}
                      </td>
                      <td className="xp-td" style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                        {formatTime(s.started_at)}
                      </td>
                    </tr>
                    {/* Expanded detail row */}
                    {isExpanded && (
                      <tr>
                        <td colSpan={7} style={{
                          padding: 'var(--xp-space-4)',
                          background: 'var(--xp-bg-base)',
                          borderBottom: '1px solid var(--xp-border-subtle)',
                        }} className="xp-animate-slide-up">
                          <div style={{ display: 'flex', gap: 'var(--xp-space-6)' }}>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                Full URL
                              </div>
                              <div style={{ fontSize: 'var(--xp-text-sm)', fontFamily: 'var(--xp-font-mono)', wordBreak: 'break-all' }}>
                                {s.url}
                              </div>
                            </div>
                            {s.error && (
                              <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                  Error
                                </div>
                                <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-danger)', fontFamily: 'var(--xp-font-mono)' }}>
                                  {s.error}
                                </div>
                              </div>
                            )}
                            <div style={{ display: 'flex', gap: 'var(--xp-space-2)', alignItems: 'flex-start' }}>
                              <button className="xp-btn xp-btn-secondary xp-btn-sm"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (s.workflow_id) {
                                    workflowsAPI.execute(s.workflow_id, { input_data: {} })
                                      .then(() => addToast('Re-run dispatched', 'success'))
                                      .catch((err) => addToast('Re-run failed: ' + err.message, 'error'));
                                  } else {
                                    addToast('No workflow ID to re-run', 'warning');
                                  }
                                }}
                              >
                                <PlayCircle size={12} /> Re-Run
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Count */}
      <div style={{
        marginTop: 'var(--xp-space-3)', fontSize: 'var(--xp-text-xs)',
        color: 'var(--xp-text-muted)', textAlign: 'right',
      }}>
        Showing {filtered.length} of {sessions.length} sessions
      </div>
    </div>
  );
}
