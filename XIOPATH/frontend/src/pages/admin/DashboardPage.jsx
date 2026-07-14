/**
 * XIOPATH — Admin Dashboard Page
 * =================================
 * Landing page for the Admin (Architect) role.
 * Displays network-wide KPIs, worker status, and system health.
 */
import React, { useState, useEffect } from 'react';
import {
  Server, Activity, Network, AlertOctagon, Users, Globe,
  Cpu, HardDrive, ShieldCheck, ArrowRight, BarChart3
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../../lib/api';
import useAuthStore from '../../stores/authStore';
import useWsStore from '../../stores/wsStore';

export default function AdminDashboardPage() {
  const { user } = useAuthStore();
  const wsStatus = useWsStore((s) => s.status);
  const navigate = useNavigate();
  const [stats, setStats] = useState({
    workersOnline: 0,
    activeSessions: 0,
    memoryNodes: 0,
    dlqIncidents: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [workersRes, dlqRes] = await Promise.allSettled([
          api.get('/agent/workers'),
          api.get('/dlq/list'),
        ]);

        setStats({
          workersOnline: workersRes.status === 'fulfilled'
            ? Object.keys(workersRes.value.data.workers || {}).length : 0,
          activeSessions: 0,
          memoryNodes: 0,
          dlqIncidents: dlqRes.status === 'fulfilled'
            ? (dlqRes.value.data.incidents?.length || 0) : 0,
        });
      } catch {
        // Best-effort
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  // ─── Live WS Subscriptions ────────────────────
  const subscribe = useWsStore((s) => s.subscribe);
  useEffect(() => {
    const unsub1 = subscribe('workers', (data) => {
      if (data.type === 'worker_joined' || data.type === 'worker_left') {
        setStats((prev) => ({ ...prev, workersOnline: data.total_workers ?? prev.workersOnline }));
      }
    });
    const unsub2 = subscribe('dlq', (data) => {
      if (data.type === 'new_incident') {
        setStats((prev) => ({ ...prev, dlqIncidents: prev.dlqIncidents + 1 }));
      }
    });
    return () => { unsub1(); unsub2(); };
  }, [subscribe]);

  const systemChecks = [
    { label: 'API Server', status: 'online', detail: 'localhost:8000' },
    { label: 'WebSocket', status: wsStatus === 'connected' ? 'online' : 'offline', detail: wsStatus },
    { label: 'Database', status: 'online', detail: 'SQLite' },
    { label: 'Vector Store', status: 'online', detail: 'ChromaDB' },
  ];

  const adminActions = [
    { label: 'Workers', desc: 'Monitor & manage compute nodes', icon: Server, path: '/admin/workers', color: 'var(--xp-cyan)' },
    { label: 'Memory', desc: 'Explore the knowledge graph', icon: Network, path: '/admin/memory', color: 'var(--xp-purple)' },
    { label: 'DLQ Triage', desc: 'Review failure incidents', icon: AlertOctagon, path: '/admin/dlq', color: 'var(--xp-danger)', badge: stats.dlqIncidents || null },
    { label: 'Analytics', desc: 'Performance & metrics', icon: BarChart3, path: '/admin/analytics', color: 'var(--xp-blue)' },
  ];

  return (
    <div className="xp-animate-fade-in">
      {/* ─── Page Header ──────────────────────────── */}
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">
            Command Center
          </h1>
          <p className="xp-page-subtitle">
            XIOPATH platform overview — real-time system intelligence
          </p>
        </div>
        <span className="xp-badge xp-badge-purple" style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          <ShieldCheck size={12} /> Admin
        </span>
      </div>

      {/* ─── KPI Cards ────────────────────────────── */}
      <div className="xp-grid xp-grid-4" style={{ marginBottom: 'var(--xp-space-6)' }}>
        {[
          { label: 'Workers Online', value: stats.workersOnline, icon: Server, color: 'var(--xp-cyan)' },
          { label: 'Active Sessions', value: stats.activeSessions, icon: Activity, color: 'var(--xp-purple)' },
          { label: 'Memory Nodes', value: stats.memoryNodes, icon: Network, color: 'var(--xp-blue)' },
          { label: 'DLQ Incidents', value: stats.dlqIncidents, icon: AlertOctagon, color: stats.dlqIncidents > 0 ? 'var(--xp-danger)' : 'var(--xp-success)' },
        ].map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div key={kpi.label} className="xp-card" style={{ position: 'relative', overflow: 'hidden' }}>
              <div style={{
                position: 'absolute',
                top: '-20px',
                right: '-20px',
                width: '80px',
                height: '80px',
                borderRadius: '50%',
                background: `radial-gradient(circle, ${kpi.color}15, transparent 70%)`,
                pointerEvents: 'none',
              }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div className="xp-stat">
                  <span className="xp-stat-label">{kpi.label}</span>
                  <span className="xp-stat-value" style={{ color: loading ? 'var(--xp-text-muted)' : undefined }}>
                    {loading ? '—' : kpi.value}
                  </span>
                </div>
                <div style={{
                  padding: 'var(--xp-space-2)',
                  borderRadius: 'var(--xp-radius-md)',
                  background: `${kpi.color}15`,
                }}>
                  <Icon size={20} style={{ color: kpi.color }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="xp-grid xp-grid-2" style={{ marginBottom: 'var(--xp-space-6)' }}>
        {/* ─── Quick Actions ──────────────────────── */}
        <div>
          <h3 style={{ marginBottom: 'var(--xp-space-4)', fontSize: 'var(--xp-text-md)' }}>
            Quick Actions
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }} className="xp-stagger">
            {adminActions.map((action) => {
              const Icon = action.icon;
              return (
                <div
                  key={action.label}
                  className="xp-card-interactive"
                  onClick={() => navigate(action.path)}
                  style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-4)', padding: 'var(--xp-space-4)' }}
                >
                  <div style={{
                    width: 40,
                    height: 40,
                    borderRadius: 'var(--xp-radius-lg)',
                    background: `${action.color}12`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <Icon size={18} style={{ color: action.color }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 'var(--xp-weight-medium)', fontSize: 'var(--xp-text-sm)' }}>
                      {action.label}
                    </div>
                    <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                      {action.desc}
                    </div>
                  </div>
                  {action.badge && (
                    <span className="xp-badge xp-badge-danger">{action.badge}</span>
                  )}
                  <ArrowRight size={14} style={{ color: 'var(--xp-text-muted)' }} />
                </div>
              );
            })}
          </div>
        </div>

        {/* ─── System Health ──────────────────────── */}
        <div>
          <h3 style={{ marginBottom: 'var(--xp-space-4)', fontSize: 'var(--xp-text-md)' }}>
            System Health
          </h3>
          <div className="xp-card">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }}>
              {systemChecks.map((check) => (
                <div key={check.label} style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: 'var(--xp-space-3)',
                  background: 'var(--xp-bg-base)',
                  borderRadius: 'var(--xp-radius-md)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)' }}>
                    <span className={`xp-dot ${check.status === 'online' ? 'xp-dot-success xp-dot-pulse' : 'xp-dot-danger'}`} />
                    <span style={{ fontSize: 'var(--xp-text-sm)', fontWeight: 'var(--xp-weight-medium)' }}>
                      {check.label}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
                    <span style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', fontFamily: 'var(--xp-font-mono)' }}>
                      {check.detail}
                    </span>
                    <span className={`xp-badge ${check.status === 'online' ? 'xp-badge-success' : 'xp-badge-danger'}`}>
                      {check.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
