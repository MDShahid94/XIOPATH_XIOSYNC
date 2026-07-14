import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Server, Activity, Cpu, Zap, RefreshCw, Play,
  Globe, Clock, Wifi, WifiOff
} from 'lucide-react';

const API_URL = "http://localhost:8000/api/v1";

/* ── helper: format seconds → human-readable uptime ── */
function formatUptime(seconds) {
  if (!seconds || seconds < 0) return '0s';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/* ── helper: relative time for heartbeats ── */
function timeAgo(iso) {
  if (!iso) return 'never';
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

/* ── worker type → gradient colours ── */
const WORKER_TYPE_STYLES = {
  colab_cpu: {
    background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
    label: 'Colab CPU',
  },
  colab_gpu: {
    background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
    label: 'Colab GPU',
  },
  admin_local: {
    background: 'linear-gradient(135deg, #10b981, #059669)',
    label: 'Local',
  },
};

/* ── inline keyframes for pulse dot ── */
const pulseKeyframes = `
@keyframes wm-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
  70%  { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}
@keyframes wm-card-in {
  from { opacity: 0; transform: translateY(12px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
`;

export default function WorkerMonitor() {
  const [workers, setWorkers] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [graphs, setGraphs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deploying, setDeploying] = useState(null); // mail_id being deployed
  const [deployStatus, setDeployStatus] = useState({});
  const [refreshing, setRefreshing] = useState(false);

  const authHeaders = useCallback(() => {
    const token = localStorage.getItem('token');
    return { Authorization: `Bearer ${token}` };
  }, []);

  /* ── data fetchers ── */
  const fetchWorkers = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/agent/workers`, {
        headers: authHeaders(),
      });
      setWorkers(res.data.workers || res.data || []);
    } catch (err) {
      console.error('Worker fetch failed', err);
    }
  }, [authHeaders]);

  const fetchProfiles = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/seed/profiles`, {
        headers: authHeaders(),
      });
      setProfiles(res.data.profiles || res.data || []);
    } catch (err) {
      console.error('Profile fetch failed', err);
    }
  }, [authHeaders]);

  const fetchGraphs = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/seed/graphs`, {
        headers: authHeaders(),
      });
      setGraphs(res.data.graphs || res.data || []);
    } catch (err) {
      console.error('Graph fetch failed', err);
    }
  }, [authHeaders]);

  /* ── initial load + polling ── */
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchWorkers(), fetchProfiles(), fetchGraphs()]);
      setLoading(false);
    };
    loadAll();

    const interval = setInterval(() => {
      fetchWorkers();
    }, 5000);

    return () => clearInterval(interval);
  }, [fetchWorkers, fetchProfiles, fetchGraphs]);

  /* ── deploy action ── */
  const handleDeploy = async (mailId) => {
    setDeploying(mailId);
    setDeployStatus((prev) => ({ ...prev, [mailId]: 'Deploying...' }));
    try {
      const res = await axios.post(
        `${API_URL}/seed/deploy`,
        { graph_name: 'colab_deploy_graph', profile_mail_id: mailId },
        { headers: authHeaders() }
      );
      setDeployStatus((prev) => ({
        ...prev,
        [mailId]: res.data.message || '✅ Deployed',
      }));
      // Refresh workers & profiles to reflect changes
      setTimeout(() => {
        fetchWorkers();
        fetchProfiles();
      }, 2000);
    } catch (err) {
      setDeployStatus((prev) => ({
        ...prev,
        [mailId]: `❌ ${err.response?.data?.detail || err.message}`,
      }));
    } finally {
      setDeploying(null);
    }
  };

  /* ── manual refresh ── */
  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchWorkers(), fetchProfiles(), fetchGraphs()]);
    setRefreshing(false);
  };

  /* ── statistics ── */
  const totalWorkers = workers.length;
  const activeWorkers = workers.filter((w) => {
    if (!w.last_heartbeat) return false;
    const staleMs = Date.now() - new Date(w.last_heartbeat).getTime();
    return staleMs < 30000; // active if heartbeat < 30s
  }).length;
  const totalTasks = workers.reduce(
    (sum, w) => sum + (w.tasks_completed || 0),
    0
  );

  /* ── is a profile recently deployed? ── */
  const isRecentlyDeployed = (profile) => {
    if (!profile.last_deployed) return false;
    const diff = Date.now() - new Date(profile.last_deployed).getTime();
    return diff < 300000; // 5 minutes
  };

  const isWorkerActive = (w) => {
    if (!w.last_heartbeat) return false;
    return Date.now() - new Date(w.last_heartbeat).getTime() < 30000;
  };

  return (
    <>
      {/* inject keyframes */}
      <style>{pulseKeyframes}</style>

      <div className="glass-panel">
        {/* ── Header ── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h2 className="gradient-text" style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: 0, fontSize: '1.5rem' }}>
              <Server size={24} /> Swarm Workers
            </h2>
            <p style={{ color: 'var(--text-muted)', margin: '4px 0 0', fontSize: '0.9rem' }}>
              Live monitoring of distributed worker fleet
            </p>
          </div>
          <button
            className="btn-secondary"
            onClick={handleRefresh}
            disabled={refreshing}
            style={{ display: 'flex', gap: '6px', alignItems: 'center' }}
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {/* ── Statistics Strip ── */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '12px',
          marginBottom: '24px',
        }}>
          {[
            { icon: <Server size={18} />, label: 'Total Workers', value: totalWorkers, color: 'var(--primary)' },
            { icon: <Wifi size={18} />, label: 'Active Now', value: activeWorkers, color: '#10b981' },
            { icon: <Zap size={18} />, label: 'Tasks Processed', value: totalTasks, color: 'var(--secondary)' },
          ].map((stat) => (
            <div
              key={stat.label}
              style={{
                background: 'rgba(0, 0, 0, 0.2)',
                borderRadius: '12px',
                padding: '16px',
                textAlign: 'center',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ color: stat.color, marginBottom: '4px', display: 'flex', justifyContent: 'center' }}>
                {stat.icon}
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, color: stat.color }}>
                {stat.value}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                {stat.label}
              </div>
            </div>
          ))}
        </div>

        {/* ── Loading / Error ── */}
        {loading ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '24px' }}>
            Loading worker data...
          </p>
        ) : error ? (
          <p style={{ color: '#ef4444', textAlign: 'center' }}>Error: {error}</p>
        ) : (
          <>
            {/* ── Worker Grid ── */}
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', fontSize: '1.1rem' }}>
              <Activity size={18} color="var(--primary)" /> Live Worker Grid
            </h3>

            {workers.length === 0 ? (
              <div style={{
                background: 'rgba(59, 130, 246, 0.08)',
                padding: '24px',
                borderRadius: '12px',
                color: 'var(--text-muted)',
                textAlign: 'center',
                marginBottom: '24px',
              }}>
                <WifiOff size={32} style={{ marginBottom: '8px', opacity: 0.5 }} />
                <p>No workers connected. Deploy a profile below to spin one up.</p>
              </div>
            ) : (
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                gap: '12px',
                marginBottom: '24px',
              }}>
                {workers.map((w) => {
                  const active = isWorkerActive(w);
                  const typeStyle = WORKER_TYPE_STYLES[w.worker_type] || WORKER_TYPE_STYLES.admin_local;
                  return (
                    <div
                      key={w.worker_id}
                      style={{
                        background: 'rgba(0, 0, 0, 0.25)',
                        border: '1px solid var(--border)',
                        borderRadius: '12px',
                        padding: '16px',
                        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                        cursor: 'default',
                        animation: 'wm-card-in 0.4s ease forwards',
                      }}
                      onMouseOver={(e) => {
                        e.currentTarget.style.transform = 'scale(1.02)';
                        e.currentTarget.style.boxShadow = '0 8px 32px rgba(59, 130, 246, 0.15)';
                      }}
                      onMouseOut={(e) => {
                        e.currentTarget.style.transform = 'scale(1)';
                        e.currentTarget.style.boxShadow = 'none';
                      }}
                    >
                      {/* card header */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          {/* status dot */}
                          <span
                            style={{
                              width: 10,
                              height: 10,
                              borderRadius: '50%',
                              display: 'inline-block',
                              background: active ? '#10b981' : '#ef4444',
                              animation: active ? 'wm-pulse 2s infinite' : 'none',
                              flexShrink: 0,
                            }}
                          />
                          <span style={{ fontWeight: 600, fontFamily: 'monospace', fontSize: '0.95rem' }}>
                            {(w.worker_id || '').substring(0, 8)}
                          </span>
                        </div>
                        {/* type badge */}
                        <span style={{
                          background: typeStyle.background,
                          color: '#fff',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          padding: '3px 10px',
                          borderRadius: '20px',
                          letterSpacing: '0.5px',
                          textTransform: 'uppercase',
                        }}>
                          {typeStyle.label}
                        </span>
                      </div>

                      {/* card body */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Clock size={14} />
                          <span>Uptime: <strong style={{ color: 'var(--text-main)' }}>{formatUptime(w.uptime_seconds)}</strong></span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Zap size={14} />
                          <span>Tasks: <strong style={{ color: 'var(--text-main)' }}>{w.tasks_completed ?? 0}</strong></span>
                        </div>
                        {w.system_info && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Cpu size={14} />
                            <span>
                              {w.system_info.python_version && `Py ${w.system_info.python_version}`}
                              {w.system_info.ram && ` · ${w.system_info.ram}`}
                              {w.system_info.gpu && ` · ${w.system_info.gpu}`}
                            </span>
                          </div>
                        )}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          {active ? <Wifi size={14} color="#10b981" /> : <WifiOff size={14} color="#ef4444" />}
                          <span>Heartbeat: <strong style={{ color: active ? '#10b981' : '#ef4444' }}>{timeAgo(w.last_heartbeat)}</strong></span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* ── Available Graphs ── */}
            {graphs.length > 0 && (
              <div style={{ marginBottom: '24px' }}>
                <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', fontSize: '1.1rem' }}>
                  <Globe size={18} color="var(--secondary)" /> Available Graphs
                </h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {graphs.map((g) => (
                    <span
                      key={g.name || g}
                      style={{
                        background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(59, 130, 246, 0.2))',
                        border: '1px solid rgba(139, 92, 246, 0.3)',
                        color: 'var(--text-main)',
                        padding: '4px 14px',
                        borderRadius: '20px',
                        fontSize: '0.8rem',
                        fontWeight: 500,
                      }}
                    >
                      {g.name || g}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* ── Swarm Profiles Table ── */}
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', fontSize: '1.1rem' }}>
              <Cpu size={18} color="var(--accent)" /> Swarm Profiles
            </h3>

            {profiles.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '16px' }}>
                No profiles configured.
              </p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{
                  width: '100%',
                  borderCollapse: 'separate',
                  borderSpacing: '0 6px',
                  fontSize: '0.88rem',
                }}>
                  <thead>
                    <tr>
                      {['Mail ID', 'Status', 'Last Deployed', 'Runtime', 'Action'].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: 'left',
                            padding: '8px 12px',
                            color: 'var(--text-muted)',
                            fontWeight: 500,
                            borderBottom: '1px solid var(--border)',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {profiles.map((p) => {
                      const recent = isRecentlyDeployed(p);
                      return (
                        <tr
                          key={p.mail_id}
                          style={{
                            background: 'rgba(0, 0, 0, 0.15)',
                            transition: 'background 0.2s',
                          }}
                          onMouseOver={(e) => (e.currentTarget.style.background = 'rgba(59, 130, 246, 0.08)')}
                          onMouseOut={(e) => (e.currentTarget.style.background = 'rgba(0, 0, 0, 0.15)')}
                        >
                          <td style={{ padding: '10px 12px', borderRadius: '8px 0 0 8px', fontFamily: 'monospace' }}>
                            {p.mail_id}
                          </td>
                          <td style={{ padding: '10px 12px' }}>
                            <span style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '6px',
                              color: p.status === 'idle' ? '#10b981' : p.status === 'running' ? 'var(--primary)' : 'var(--text-muted)',
                            }}>
                              <span style={{
                                width: 8,
                                height: 8,
                                borderRadius: '50%',
                                background: p.status === 'idle' ? '#10b981' : p.status === 'running' ? 'var(--primary)' : '#64748b',
                              }} />
                              {p.status || 'unknown'}
                            </span>
                          </td>
                          <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>
                            {p.last_deployed ? new Date(p.last_deployed).toLocaleString() : '—'}
                          </td>
                          <td style={{ padding: '10px 12px' }}>
                            <span style={{
                              background: p.runtime_type === 'gpu'
                                ? 'linear-gradient(135deg, #8b5cf6, #7c3aed)'
                                : 'linear-gradient(135deg, #3b82f6, #2563eb)',
                              color: '#fff',
                              fontSize: '0.72rem',
                              fontWeight: 600,
                              padding: '2px 10px',
                              borderRadius: '12px',
                              textTransform: 'uppercase',
                            }}>
                              {p.runtime_type || 'cpu'}
                            </span>
                          </td>
                          <td style={{ padding: '10px 12px', borderRadius: '0 8px 8px 0' }}>
                            <button
                              className="btn-primary"
                              disabled={deploying === p.mail_id || recent}
                              onClick={() => handleDeploy(p.mail_id)}
                              style={{
                                padding: '6px 16px',
                                fontSize: '0.8rem',
                                opacity: recent ? 0.5 : 1,
                              }}
                            >
                              <Play size={14} />
                              {deploying === p.mail_id ? 'Deploying...' : 'Deploy'}
                            </button>
                            {deployStatus[p.mail_id] && (
                              <span style={{
                                marginLeft: '8px',
                                fontSize: '0.78rem',
                                color: deployStatus[p.mail_id].includes('❌') ? '#ef4444' : '#10b981',
                              }}>
                                {deployStatus[p.mail_id]}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
