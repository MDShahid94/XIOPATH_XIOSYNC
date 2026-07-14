/**
 * XIOPATH — DLQ Triage Page (Admin)
 * ====================================
 * Dead Letter Queue incident management.
 * Review, retry, or dismiss failed workflow steps.
 */
import React, { useState, useEffect } from 'react';
import {
  AlertOctagon, RefreshCw, Play, Trash2, Eye, Search,
  Clock, Globe, AlertTriangle, XCircle, ChevronDown,
  CheckCircle, Loader2, Filter
} from 'lucide-react';
import api from '../../lib/api';

const SEVERITY = {
  critical: { color: 'var(--xp-danger)', badge: 'xp-badge-danger', label: 'Critical' },
  high:     { color: 'var(--xp-warning)', badge: 'xp-badge-warning', label: 'High' },
  medium:   { color: 'var(--xp-info)', badge: 'xp-badge-info', label: 'Medium' },
  low:      { color: 'var(--xp-text-muted)', badge: 'xp-badge-neutral', label: 'Low' },
};

export default function DLQPage() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [filter, setFilter] = useState('all');

  useEffect(() => { fetchIncidents(); }, []);

  const fetchIncidents = async () => {
    setLoading(true);
    try {
      const res = await api.get('/dlq/list');
      setIncidents(res.data.incidents || []);
    } catch {
      setIncidents([
        {
          id: 'dlq_001', session_id: 'xp_demo_002', intent: 'search_products', domain: 'amazon.com',
          error: 'Element not found: #search-results', action_type: 'click', selector: '#search-results',
          severity: 'high', status: 'open', retry_count: 2,
          timestamp: new Date(Date.now() - 7200000).toISOString(),
          stack_trace: 'TimeoutError: Waiting for selector "#search-results" failed\n  at click_element (agent_loop.py:142)\n  at execute_step (agent_loop.py:89)',
        },
        {
          id: 'dlq_002', session_id: 'xp_demo_005', intent: 'submit_form', domain: 'forms.google.com',
          error: 'CAPTCHA detected — plugin not available', action_type: 'submit', selector: 'form[action*=response]',
          severity: 'critical', status: 'open', retry_count: 0,
          timestamp: new Date(Date.now() - 3600000).toISOString(),
          stack_trace: 'CaptchaError: CAPTCHA challenge detected\n  at check_captcha (plugin_manager.py:67)',
        },
        {
          id: 'dlq_003', session_id: 'xp_demo_003', intent: 'extract_data', domain: 'linkedin.com',
          error: 'Rate limited: 429 Too Many Requests', action_type: 'extract', selector: '.search-results__list',
          severity: 'medium', status: 'dismissed', retry_count: 3,
          timestamp: new Date(Date.now() - 86400000).toISOString(),
        },
      ]);
    }
    setLoading(false);
  };

  const handleRetry = async (id) => {
    try {
      await api.post(`/dlq/retry/${id}`);
      fetchIncidents();
    } catch {
      setIncidents((prev) => prev.map((inc) =>
        inc.id === id ? { ...inc, retry_count: inc.retry_count + 1, status: 'retrying' } : inc
      ));
    }
  };

  const handleDismiss = async (id) => {
    try {
      await api.post(`/dlq/dismiss/${id}`);
      fetchIncidents();
    } catch {
      setIncidents((prev) => prev.map((inc) =>
        inc.id === id ? { ...inc, status: 'dismissed' } : inc
      ));
    }
  };

  const filtered = filter === 'all' ? incidents : incidents.filter((i) => i.status === filter);
  const openCount = incidents.filter((i) => i.status === 'open').length;

  const formatTime = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
           d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="xp-animate-fade-in">
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">DLQ Triage</h1>
          <p className="xp-page-subtitle">Review and resolve failed workflow incidents</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)' }}>
          {openCount > 0 && (
            <span className="xp-badge xp-badge-danger" style={{ fontSize: 'var(--xp-text-sm)', padding: '4px 12px' }}>
              {openCount} open
            </span>
          )}
          <button className="xp-btn xp-btn-secondary" onClick={fetchIncidents} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'xp-animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="xp-tabs" style={{ marginBottom: 'var(--xp-space-5)' }}>
        {['all', 'open', 'retrying', 'dismissed'].map((f) => (
          <button key={f} className={`xp-tab ${filter === f ? 'xp-tab-active' : ''}`}
            onClick={() => setFilter(f)}
            style={{ textTransform: 'capitalize' }}
          >
            {f} {f === 'all' ? `(${incidents.length})` : `(${incidents.filter(i => i.status === f).length})`}
          </button>
        ))}
      </div>

      {/* Incident List */}
      {loading ? (
        <div className="xp-stagger">
          {[1, 2, 3].map((i) => <div key={i} className="xp-skeleton" style={{ height: '100px', marginBottom: 'var(--xp-space-3)' }} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="xp-card">
          <div className="xp-empty">
            <CheckCircle size={40} style={{ color: 'var(--xp-success)' }} />
            <div className="xp-empty-title">{filter === 'all' ? 'No incidents' : `No ${filter} incidents`}</div>
            <div className="xp-empty-desc">All clear — no workflow failures to review.</div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }} className="xp-stagger">
          {filtered.map((inc) => {
            const sev = SEVERITY[inc.severity] || SEVERITY.medium;
            const isExpanded = expandedId === inc.id;
            return (
              <div key={inc.id} className="xp-card" style={{
                borderLeft: `3px solid ${sev.color}`,
                opacity: inc.status === 'dismissed' ? 0.6 : 1,
              }}>
                {/* Header row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)', marginBottom: isExpanded ? 'var(--xp-space-4)' : 0 }}>
                  <AlertOctagon size={18} style={{ color: sev.color, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)', flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 'var(--xp-weight-semibold)', fontSize: 'var(--xp-text-sm)' }}>
                        {inc.error}
                      </span>
                      <span className={`xp-badge ${sev.badge}`}>{sev.label}</span>
                      {inc.status === 'dismissed' && <span className="xp-badge xp-badge-neutral">Dismissed</span>}
                    </div>
                    <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', display: 'flex', gap: 'var(--xp-space-3)', marginTop: '4px' }}>
                      <span><Globe size={10} style={{ verticalAlign: 'middle' }} /> {inc.domain}</span>
                      <span>Intent: {inc.intent}</span>
                      <span><Clock size={10} style={{ verticalAlign: 'middle' }} /> {formatTime(inc.timestamp)}</span>
                      <span>Retries: {inc.retry_count}</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--xp-space-1)', flexShrink: 0 }}>
                    <button className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm" data-tooltip="Inspect"
                      onClick={() => setExpandedId(isExpanded ? null : inc.id)}>
                      <Eye size={14} />
                    </button>
                    {inc.status === 'open' && (
                      <>
                        <button className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm" data-tooltip="Retry"
                          onClick={() => handleRetry(inc.id)} style={{ color: 'var(--xp-success)' }}>
                          <Play size={14} />
                        </button>
                        <button className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm" data-tooltip="Dismiss"
                          onClick={() => handleDismiss(inc.id)} style={{ color: 'var(--xp-text-muted)' }}>
                          <XCircle size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Expanded details */}
                {isExpanded && (
                  <div className="xp-animate-slide-up" style={{
                    padding: 'var(--xp-space-4)', background: 'var(--xp-bg-void)',
                    borderRadius: 'var(--xp-radius-md)',
                  }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--xp-space-3)', marginBottom: 'var(--xp-space-3)' }}>
                      <div><span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>Session ID</span><br/><code style={{ fontSize: '11px' }}>{inc.session_id}</code></div>
                      <div><span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>Action Type</span><br/><code style={{ fontSize: '11px' }}>{inc.action_type}</code></div>
                      <div style={{ gridColumn: '1 / -1' }}><span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>Selector</span><br/><code style={{ fontSize: '11px', color: 'var(--xp-purple)' }}>{inc.selector}</code></div>
                    </div>
                    {inc.stack_trace && (
                      <div>
                        <span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>Stack Trace</span>
                        <pre style={{
                          marginTop: '4px', padding: 'var(--xp-space-3)',
                          background: 'var(--xp-bg-base)', borderRadius: 'var(--xp-radius-sm)',
                          fontSize: '11px', fontFamily: 'var(--xp-font-mono)',
                          color: 'var(--xp-danger)', overflow: 'auto', whiteSpace: 'pre-wrap',
                        }}>
                          {inc.stack_trace}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
