/**
 * XIOPATH — Worker Management Page (Admin)
 * ============================================
 * Real-time worker monitoring grid with heartbeat status,
 * task assignments, and deployment controls.
 */
import React, { useState, useEffect } from 'react';
import {
  Server, RefreshCw, Wifi, WifiOff, Cpu, Clock, Activity,
  Zap, Play, Trash2, AlertTriangle, CheckCircle, Loader2
} from 'lucide-react';
import api from '../../lib/api';
import useWsStore from '../../stores/wsStore';

const WORKER_STATUS = {
  idle:        { color: 'var(--xp-success)', label: 'Idle', dotClass: 'xp-dot-success' },
  busy:        { color: 'var(--xp-warning)', label: 'Busy', dotClass: 'xp-dot-warning' },
  stale:       { color: 'var(--xp-danger)',  label: 'Stale', dotClass: 'xp-dot-danger' },
  connecting:  { color: 'var(--xp-info)',    label: 'Connecting', dotClass: 'xp-dot-info' },
};

export default function WorkersPage() {
  const [workers, setWorkers] = useState({});
  const [loading, setLoading] = useState(true);
  const subscribe = useWsStore((s) => s.subscribe);

  useEffect(() => { fetchWorkers(); }, []);

  // Subscribe to live worker updates
  useEffect(() => {
    const unsub = subscribe('workers', (data) => {
      if (data.type === 'worker_joined' || data.type === 'worker_left') {
        // Refetch the full worker list for consistency
        fetchWorkers();
      } else if (data.worker_id) {
        setWorkers((prev) => ({
          ...prev,
          [data.worker_id]: { ...prev[data.worker_id], ...data },
        }));
      }
    });
    return unsub;
  }, [subscribe]);

  const fetchWorkers = async () => {
    setLoading(true);
    try {
      const res = await api.get('/agent/workers');
      setWorkers(res.data.workers || {});
    } catch {
      // Mock data for demo
      setWorkers({
        'worker_colab_01': {
          worker_id: 'worker_colab_01', type: 'colab', status: 'idle',
          last_heartbeat: new Date(Date.now() - 15000).toISOString(),
          current_task: null, connected_at: new Date(Date.now() - 3600000).toISOString(),
          profile: 'lifelonglearnersgroup@gmail.com',
        },
        'worker_colab_02': {
          worker_id: 'worker_colab_02', type: 'colab', status: 'busy',
          last_heartbeat: new Date(Date.now() - 5000).toISOString(),
          current_task: 'xp_task_abc123', connected_at: new Date(Date.now() - 7200000).toISOString(),
          profile: 'creativetech.raiganj@gmail.com',
        },
      });
    }
    setLoading(false);
  };

  const workerList = Object.values(workers);
  const onlineCount = workerList.filter((w) => w.status !== 'stale').length;

  const getHeartbeatAge = (ts) => {
    if (!ts) return '—';
    const age = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
    if (age < 60) return `${age}s ago`;
    if (age < 3600) return `${Math.floor(age / 60)}m ago`;
    return `${Math.floor(age / 3600)}h ago`;
  };

  const getUptime = (ts) => {
    if (!ts) return '—';
    const mins = Math.floor((Date.now() - new Date(ts).getTime()) / 60000);
    if (mins < 60) return `${mins}m`;
    return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  };

  return (
    <div className="xp-animate-fade-in">
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Worker Management</h1>
          <p className="xp-page-subtitle">Monitor and manage compute nodes across the swarm</p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--xp-space-2)' }}>
          <button className="xp-btn xp-btn-secondary" onClick={fetchWorkers} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'xp-animate-spin' : ''} /> Refresh
          </button>
          <button className="xp-btn xp-btn-primary">
            <Play size={14} /> Deploy Worker
          </button>
        </div>
      </div>

      {/* ─── Stats ────────────────────────────────── */}
      <div className="xp-grid xp-grid-4" style={{ marginBottom: 'var(--xp-space-6)' }}>
        {[
          { label: 'Total Workers', value: workerList.length, icon: Server, color: 'var(--xp-cyan)' },
          { label: 'Online', value: onlineCount, icon: Wifi, color: 'var(--xp-success)' },
          { label: 'Busy', value: workerList.filter(w => w.status === 'busy').length, icon: Activity, color: 'var(--xp-warning)' },
          { label: 'Stale', value: workerList.filter(w => w.status === 'stale').length, icon: AlertTriangle, color: 'var(--xp-danger)' },
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

      {/* ─── Worker Grid ──────────────────────────── */}
      {loading ? (
        <div className="xp-grid xp-grid-2 xp-stagger">
          {[1, 2, 3, 4].map((i) => <div key={i} className="xp-skeleton" style={{ height: '160px' }} />)}
        </div>
      ) : workerList.length === 0 ? (
        <div className="xp-card">
          <div className="xp-empty">
            <Server size={40} className="xp-empty-icon" />
            <div className="xp-empty-title">No workers connected</div>
            <div className="xp-empty-desc">Deploy a Colab worker to start processing tasks.</div>
          </div>
        </div>
      ) : (
        <div className="xp-grid xp-grid-2 xp-stagger">
          {workerList.map((w) => {
            const st = WORKER_STATUS[w.status] || WORKER_STATUS.idle;
            return (
              <div key={w.worker_id} className="xp-card" style={{
                borderColor: w.status === 'stale' ? 'rgba(239,68,68,0.3)' : undefined,
              }}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--xp-space-4)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)' }}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 'var(--xp-radius-lg)',
                      background: `${st.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Server size={18} style={{ color: st.color }} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 'var(--xp-weight-semibold)', fontSize: 'var(--xp-text-sm)' }}>
                        {w.worker_id}
                      </div>
                      <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                        {w.type || 'colab'} · {w.profile || 'No profile'}
                      </div>
                    </div>
                  </div>
                  <span className={`xp-badge ${
                    w.status === 'idle' ? 'xp-badge-success' :
                    w.status === 'busy' ? 'xp-badge-warning' :
                    w.status === 'stale' ? 'xp-badge-danger' : 'xp-badge-info'
                  }`} style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    <span className={`xp-dot ${st.dotClass}`} style={{ width: '6px', height: '6px' }} />
                    {st.label}
                  </span>
                </div>

                {/* Details */}
                <div style={{
                  display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--xp-space-2)',
                  padding: 'var(--xp-space-3)', background: 'var(--xp-bg-base)',
                  borderRadius: 'var(--xp-radius-md)', fontSize: 'var(--xp-text-xs)',
                }}>
                  <div>
                    <div style={{ color: 'var(--xp-text-muted)', marginBottom: '2px' }}>Heartbeat</div>
                    <div style={{ fontFamily: 'var(--xp-font-mono)', color: w.status === 'stale' ? 'var(--xp-danger)' : 'var(--xp-text-primary)' }}>
                      {getHeartbeatAge(w.last_heartbeat)}
                    </div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--xp-text-muted)', marginBottom: '2px' }}>Uptime</div>
                    <div style={{ fontFamily: 'var(--xp-font-mono)' }}>{getUptime(w.connected_at)}</div>
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <div style={{ color: 'var(--xp-text-muted)', marginBottom: '2px' }}>Current Task</div>
                    <div style={{ fontFamily: 'var(--xp-font-mono)', color: w.current_task ? 'var(--xp-cyan)' : 'var(--xp-text-muted)' }}>
                      {w.current_task || 'None'}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
