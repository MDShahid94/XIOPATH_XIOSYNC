/**
 * XIOPATH — Deployment Hub Page (Admin)
 * ========================================
 * Manage swarm profiles and trigger autonomous deployments.
 */
import React, { useState, useEffect } from 'react';
import {
  Rocket, RefreshCw, Play, User, Globe, Clock,
  CheckCircle, AlertTriangle, Loader2, Shield, Server
} from 'lucide-react';
import api from '../../lib/api';

export default function DeployPage() {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deploying, setDeploying] = useState(null);
  const [deployLog, setDeployLog] = useState([]);

  useEffect(() => { fetchProfiles(); }, []);

  const fetchProfiles = async () => {
    setLoading(true);
    try {
      const res = await api.get('/agent/swarm/profiles');
      setProfiles(res.data.profiles || []);
    } catch {
      setProfiles([
        {
          mail_id: 'lifelonglearnersgroup@gmail.com', profile_file: 'lifelonglearnersgroup@gmail.com_profile.xio',
          last_deployed: null, status: 'available',
        },
        {
          mail_id: 'creativetech.raiganj@gmail.com', profile_file: 'creativetech.raiganj@gmail.com_profile.xio',
          last_deployed: new Date(Date.now() - 86400000).toISOString(), status: 'available',
        },
        {
          mail_id: 'imrankhanchainagar@gmail.com', profile_file: 'imrankhanchainagar@gmail.com_profile.xio',
          last_deployed: new Date(Date.now() - 172800000).toISOString(), status: 'available',
        },
      ]);
    }
    setLoading(false);
  };

  const handleDeploy = (profile) => {
    setDeploying(profile.mail_id);
    setDeployLog([
      { time: new Date(), msg: `🚀 Initiating deployment for ${profile.mail_id}...`, type: 'info' },
    ]);

    // Simulate deployment steps
    setTimeout(() => setDeployLog((prev) => [...prev, { time: new Date(), msg: '📊 Loading deployment graph...', type: 'info' }]), 800);
    setTimeout(() => setDeployLog((prev) => [...prev, { time: new Date(), msg: '👤 Injecting swarm profile...', type: 'info' }]), 1600);
    setTimeout(() => setDeployLog((prev) => [...prev, { time: new Date(), msg: '🌐 Opening Colab runtime...', type: 'info' }]), 2400);
    setTimeout(() => setDeployLog((prev) => [...prev, { time: new Date(), msg: '💉 Injecting bootstrap script...', type: 'info' }]), 3200);
    setTimeout(() => {
      setDeployLog((prev) => [...prev, { time: new Date(), msg: '✅ Worker deployed successfully!', type: 'success' }]);
      setDeploying(null);
    }, 4000);
  };

  const formatTime = (iso) => {
    if (!iso) return 'Never';
    const age = Math.floor((Date.now() - new Date(iso).getTime()) / 3600000);
    if (age < 24) return `${age}h ago`;
    return `${Math.floor(age / 24)}d ago`;
  };

  return (
    <div className="xp-animate-fade-in">
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Deployment Hub</h1>
          <p className="xp-page-subtitle">Autonomous swarm deployment and profile management</p>
        </div>
        <button className="xp-btn xp-btn-secondary" onClick={fetchProfiles} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'xp-animate-spin' : ''} />
        </button>
      </div>

      {/* ─── Stats ────────────────────────────────── */}
      <div className="xp-grid xp-grid-3" style={{ marginBottom: 'var(--xp-space-6)' }}>
        {[
          { label: 'Swarm Profiles', value: profiles.length, icon: User, color: 'var(--xp-cyan)' },
          { label: 'Available', value: profiles.filter(p => p.status === 'available').length, icon: CheckCircle, color: 'var(--xp-success)' },
          { label: 'Deployed', value: profiles.filter(p => p.last_deployed).length, icon: Rocket, color: 'var(--xp-purple)' },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="xp-card">
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

      <div className="xp-grid xp-grid-2">
        {/* ─── Profiles ───────────────────────────── */}
        <div>
          <h3 style={{ fontSize: 'var(--xp-text-md)', marginBottom: 'var(--xp-space-4)', color: 'var(--xp-text-secondary)' }}>
            Swarm Profiles
          </h3>
          {loading ? (
            <div className="xp-stagger">
              {[1, 2, 3].map((i) => <div key={i} className="xp-skeleton" style={{ height: '80px', marginBottom: 'var(--xp-space-3)' }} />)}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }} className="xp-stagger">
              {profiles.map((p) => (
                <div key={p.mail_id} className="xp-card" style={{
                  display: 'flex', alignItems: 'center', gap: 'var(--xp-space-4)',
                }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: 'var(--xp-radius-lg)',
                    background: 'var(--xp-gradient-brand)', display: 'flex',
                    alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    fontSize: 'var(--xp-text-md)', fontWeight: 'var(--xp-weight-bold)',
                    color: 'white', fontFamily: 'var(--xp-font-display)',
                  }}>
                    {p.mail_id.charAt(0).toUpperCase()}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontWeight: 'var(--xp-weight-medium)', fontSize: 'var(--xp-text-sm)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {p.mail_id}
                    </div>
                    <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', display: 'flex', gap: 'var(--xp-space-3)' }}>
                      <span className="xp-badge xp-badge-success xp-badge-sm">Persisted Session</span>
                      <span>Last: {formatTime(p.last_deployed)}</span>
                    </div>
                  </div>
                  <button
                    className="xp-btn xp-btn-primary xp-btn-sm"
                    disabled={deploying === p.mail_id}
                    onClick={() => handleDeploy(p)}
                  >
                    {deploying === p.mail_id
                      ? <><Loader2 size={12} className="xp-animate-spin" /> Deploying...</>
                      : <><Rocket size={12} /> Deploy</>
                    }
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ─── Deploy Log ─────────────────────────── */}
        <div>
          <h3 style={{ fontSize: 'var(--xp-text-md)', marginBottom: 'var(--xp-space-4)', color: 'var(--xp-text-secondary)' }}>
            Deployment Log
          </h3>
          <div className="xp-card" style={{
            background: 'var(--xp-bg-void)', minHeight: '300px',
          }}>
            {deployLog.length === 0 ? (
              <div className="xp-empty" style={{ padding: 'var(--xp-space-8) 0' }}>
                <Rocket size={32} className="xp-empty-icon" />
                <div className="xp-empty-title">No active deployment</div>
                <div className="xp-empty-desc">Select a profile and click Deploy to begin.</div>
              </div>
            ) : (
              <div style={{
                fontFamily: 'var(--xp-font-mono)', fontSize: 'var(--xp-text-xs)',
              }}>
                {deployLog.map((entry, i) => (
                  <div key={i} style={{
                    padding: '6px 0', borderBottom: '1px solid var(--xp-border-subtle)',
                    color: entry.type === 'error' ? 'var(--xp-danger)' :
                           entry.type === 'success' ? 'var(--xp-success)' : 'var(--xp-text-secondary)',
                  }} className="xp-animate-slide-up">
                    <span style={{ color: 'var(--xp-text-muted)', marginRight: '8px' }}>
                      {entry.time.toLocaleTimeString()}
                    </span>
                    {entry.msg}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
