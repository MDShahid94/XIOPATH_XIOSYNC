/**
 * XIOPATH — Consensus Dashboard Page (Admin)
 * =============================================
 * Visualize the consensus engine's voting activity,
 * tier distribution, and promotion/demotion events.
 */
import React, { useState, useEffect } from 'react';
import {
  ShieldCheck, RefreshCw, TrendingUp, TrendingDown,
  BarChart3, Layers, Vote, ArrowUpCircle, ArrowDownCircle,
  Clock, Globe
} from 'lucide-react';
import api from '../../lib/api';

export default function ConsensusPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await api.get('/memory/consensus/stats');
      setData(res.data);
    } catch {
      // Mock data
      setData({
        tier_distribution: { server_primary: 45, server_secondary: 128, local_primary: 312, local_secondary: 567 },
        recent_promotions: [
          { intent: 'login_action', from: 'server_secondary', to: 'server_primary', votes: 12, timestamp: new Date(Date.now() - 3600000).toISOString() },
          { intent: 'click_submit', from: 'local_primary', to: 'server_secondary', votes: 8, timestamp: new Date(Date.now() - 7200000).toISOString() },
          { intent: 'navigate_home', from: 'local_secondary', to: 'local_primary', votes: 5, timestamp: new Date(Date.now() - 14400000).toISOString() },
        ],
        recent_demotions: [
          { intent: 'old_selector_click', from: 'server_secondary', to: 'local_primary', reason: 'Low confidence (0.2)', timestamp: new Date(Date.now() - 86400000).toISOString() },
        ],
        total_votes_24h: 47,
        pending_reviews: 3,
      });
    }
    setLoading(false);
  };

  const tierColors = {
    server_primary: 'var(--xp-success)',
    server_secondary: 'var(--xp-cyan)',
    local_primary: 'var(--xp-purple)',
    local_secondary: 'var(--xp-text-muted)',
  };

  const tierLabels = {
    server_primary: 'Server Primary',
    server_secondary: 'Server Secondary',
    local_primary: 'Local Primary',
    local_secondary: 'Local Secondary',
  };

  const totalNodes = data ? Object.values(data.tier_distribution).reduce((a, b) => a + b, 0) : 0;

  const formatTime = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    const age = Math.floor((Date.now() - d.getTime()) / 60000);
    if (age < 60) return `${age}m ago`;
    if (age < 1440) return `${Math.floor(age / 60)}h ago`;
    return `${Math.floor(age / 1440)}d ago`;
  };

  return (
    <div className="xp-animate-fade-in">
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Consensus Dashboard</h1>
          <p className="xp-page-subtitle">Monitor the Bayesian EMA voting engine and tier transitions</p>
        </div>
        <button className="xp-btn xp-btn-secondary" onClick={fetchData} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'xp-animate-spin' : ''} />
        </button>
      </div>

      {/* ─── Stats ────────────────────────────────── */}
      <div className="xp-grid xp-grid-4" style={{ marginBottom: 'var(--xp-space-6)' }}>
        {[
          { label: 'Total Nodes', value: totalNodes, icon: Layers, color: 'var(--xp-cyan)' },
          { label: 'Votes (24h)', value: data?.total_votes_24h || 0, icon: BarChart3, color: 'var(--xp-purple)' },
          { label: 'Promotions', value: data?.recent_promotions?.length || 0, icon: TrendingUp, color: 'var(--xp-success)' },
          { label: 'Pending Review', value: data?.pending_reviews || 0, icon: ShieldCheck, color: 'var(--xp-warning)' },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="xp-card" style={{ position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: '-20px', right: '-20px', width: '80px', height: '80px', borderRadius: '50%', background: `radial-gradient(circle, ${s.color}15, transparent 70%)`, pointerEvents: 'none' }} />
              <div className="xp-stat">
                <span className="xp-stat-label">{s.label}</span>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span className="xp-stat-value">{loading ? '—' : s.value}</span>
                  <Icon size={20} style={{ color: s.color }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="xp-grid xp-grid-2" style={{ marginBottom: 'var(--xp-space-6)' }}>
        {/* ─── Tier Distribution ──────────────────── */}
        <div className="xp-card">
          <h3 style={{ fontSize: 'var(--xp-text-md)', marginBottom: 'var(--xp-space-4)' }}>
            <Layers size={16} style={{ verticalAlign: 'middle', marginRight: '8px', color: 'var(--xp-cyan)' }} />
            Tier Distribution
          </h3>
          {data && Object.entries(data.tier_distribution).map(([tier, count]) => {
            const pct = totalNodes > 0 ? (count / totalNodes * 100) : 0;
            return (
              <div key={tier} style={{ marginBottom: 'var(--xp-space-3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--xp-text-sm)', marginBottom: '4px' }}>
                  <span style={{ fontWeight: 'var(--xp-weight-medium)' }}>{tierLabels[tier]}</span>
                  <span style={{ fontFamily: 'var(--xp-font-mono)', fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                    {count} ({pct.toFixed(1)}%)
                  </span>
                </div>
                <div style={{
                  height: '6px', background: 'var(--xp-bg-base)', borderRadius: 'var(--xp-radius-full)', overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%', width: `${pct}%`, background: tierColors[tier],
                    borderRadius: 'var(--xp-radius-full)', transition: 'width 500ms ease',
                  }} />
                </div>
              </div>
            );
          })}
        </div>

        {/* ─── Recent Activity ────────────────────── */}
        <div className="xp-card">
          <h3 style={{ fontSize: 'var(--xp-text-md)', marginBottom: 'var(--xp-space-4)' }}>
            <TrendingUp size={16} style={{ verticalAlign: 'middle', marginRight: '8px', color: 'var(--xp-success)' }} />
            Recent Activity
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }}>
            {data?.recent_promotions?.map((p, i) => (
              <div key={`p-${i}`} style={{
                display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)',
                padding: 'var(--xp-space-3)', background: 'var(--xp-bg-base)',
                borderRadius: 'var(--xp-radius-md)', borderLeft: '3px solid var(--xp-success)',
              }}>
                <ArrowUpCircle size={16} style={{ color: 'var(--xp-success)', flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'var(--xp-weight-medium)', fontSize: 'var(--xp-text-sm)' }}>{p.intent}</div>
                  <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                    {tierLabels[p.from]} → {tierLabels[p.to]} · {p.votes} votes
                  </div>
                </div>
                <span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>{formatTime(p.timestamp)}</span>
              </div>
            ))}
            {data?.recent_demotions?.map((d, i) => (
              <div key={`d-${i}`} style={{
                display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)',
                padding: 'var(--xp-space-3)', background: 'var(--xp-bg-base)',
                borderRadius: 'var(--xp-radius-md)', borderLeft: '3px solid var(--xp-danger)',
              }}>
                <ArrowDownCircle size={16} style={{ color: 'var(--xp-danger)', flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'var(--xp-weight-medium)', fontSize: 'var(--xp-text-sm)' }}>{d.intent}</div>
                  <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                    {tierLabels[d.from]} → {tierLabels[d.to]} · {d.reason}
                  </div>
                </div>
                <span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>{formatTime(d.timestamp)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
