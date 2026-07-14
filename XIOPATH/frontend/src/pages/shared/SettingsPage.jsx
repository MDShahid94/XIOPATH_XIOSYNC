/**
 * XIOPATH — Settings Page
 * =========================
 * Application settings: profile, connection, preferences.
 * Shared between Client and Admin roles.
 */
import React, { useState, useEffect } from 'react';
import {
  Settings, User, Globe, Wifi, WifiOff, Server, Palette,
  Save, RefreshCw, CheckCircle, AlertTriangle, ExternalLink
} from 'lucide-react';
import api, { API_BASE } from '../../lib/api';
import useAuthStore from '../../stores/authStore';
import useWsStore from '../../stores/wsStore';

export default function SettingsPage() {
  const { user, logout } = useAuthStore();
  const wsStatus = useWsStore((s) => s.status);
  const wsConnect = useWsStore((s) => s.connect);
  const wsDisconnect = useWsStore((s) => s.disconnect);

  const [apiHealth, setApiHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const checkHealth = async () => {
    setHealthLoading(true);
    try {
      const res = await api.get('/health');
      setApiHealth(res.data);
    } catch (err) {
      setApiHealth({ status: 'unreachable', error: err.message });
    }
    setHealthLoading(false);
  };

  useEffect(() => { checkHealth(); }, []);

  return (
    <div className="xp-animate-fade-in">
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Settings</h1>
          <p className="xp-page-subtitle">Configure your XIOPATH workspace</p>
        </div>
      </div>

      <div className="xp-grid xp-grid-2">
        {/* ─── Profile ────────────────────────────── */}
        <div className="xp-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)', marginBottom: 'var(--xp-space-5)' }}>
            <User size={18} style={{ color: 'var(--xp-cyan)' }} />
            <h3 style={{ fontSize: 'var(--xp-text-md)', margin: 0 }}>Profile</h3>
          </div>

          <div style={{
            display: 'flex', alignItems: 'center', gap: 'var(--xp-space-4)',
            padding: 'var(--xp-space-4)', background: 'var(--xp-bg-base)',
            borderRadius: 'var(--xp-radius-lg)', marginBottom: 'var(--xp-space-4)',
          }}>
            <div className="xp-avatar" style={{ width: 48, height: 48, fontSize: 'var(--xp-text-md)' }}>
              {user?.username?.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <div style={{ fontWeight: 'var(--xp-weight-semibold)', fontSize: 'var(--xp-text-md)' }}>
                {user?.username}
              </div>
              <span className="xp-badge xp-badge-cyan" style={{ textTransform: 'capitalize', marginTop: '4px' }}>
                {user?.role}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--xp-text-sm)' }}>
              <span style={{ color: 'var(--xp-text-muted)' }}>User ID</span>
              <span className="xp-mono" style={{ fontSize: 'var(--xp-text-xs)' }}>{user?.id || '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--xp-text-sm)' }}>
              <span style={{ color: 'var(--xp-text-muted)' }}>JWT Token</span>
              <span className="xp-mono" style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-success)' }}>Active</span>
            </div>
          </div>
        </div>

        {/* ─── Connection ─────────────────────────── */}
        <div className="xp-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)', marginBottom: 'var(--xp-space-5)' }}>
            <Server size={18} style={{ color: 'var(--xp-purple)' }} />
            <h3 style={{ fontSize: 'var(--xp-text-md)', margin: 0 }}>Connection</h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }}>
            {/* API Server */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: 'var(--xp-space-3)', background: 'var(--xp-bg-base)',
              borderRadius: 'var(--xp-radius-md)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
                <span className={`xp-dot ${apiHealth?.status === 'healthy' ? 'xp-dot-success xp-dot-pulse' : 'xp-dot-danger'}`} />
                <span style={{ fontSize: 'var(--xp-text-sm)', fontWeight: 'var(--xp-weight-medium)' }}>API Server</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
                <span className="xp-mono" style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                  {API_BASE}
                </span>
                <button className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-xs" onClick={checkHealth}>
                  <RefreshCw size={12} className={healthLoading ? 'xp-animate-spin' : ''} />
                </button>
              </div>
            </div>

            {/* WebSocket */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: 'var(--xp-space-3)', background: 'var(--xp-bg-base)',
              borderRadius: 'var(--xp-radius-md)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
                <span className={`xp-dot ${wsStatus === 'connected' ? 'xp-dot-success xp-dot-pulse' : 'xp-dot-danger'}`} />
                <span style={{ fontSize: 'var(--xp-text-sm)', fontWeight: 'var(--xp-weight-medium)' }}>WebSocket</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
                <span className={`xp-badge ${wsStatus === 'connected' ? 'xp-badge-success' : 'xp-badge-danger'}`}>
                  {wsStatus}
                </span>
                <button className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-xs"
                  onClick={() => wsStatus === 'connected' ? wsDisconnect() : wsConnect()}
                >
                  {wsStatus === 'connected' ? <WifiOff size={12} /> : <Wifi size={12} />}
                </button>
              </div>
            </div>

            {/* Uptime */}
            {apiHealth?.uptime_seconds && (
              <div style={{
                padding: 'var(--xp-space-3)', background: 'var(--xp-bg-base)',
                borderRadius: 'var(--xp-radius-md)', fontSize: 'var(--xp-text-sm)',
                display: 'flex', justifyContent: 'space-between',
              }}>
                <span style={{ color: 'var(--xp-text-muted)' }}>Server Uptime</span>
                <span className="xp-mono" style={{ fontSize: 'var(--xp-text-xs)' }}>
                  {Math.floor(apiHealth.uptime_seconds / 60)}m {Math.floor(apiHealth.uptime_seconds % 60)}s
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ─── About ────────────────────────────────── */}
      <div className="xp-card" style={{ marginTop: 'var(--xp-space-5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)' }}>
            <div style={{
              width: 36, height: 36, borderRadius: 'var(--xp-radius-md)',
              background: 'var(--xp-gradient-brand)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 'var(--xp-text-md)', fontWeight: 'var(--xp-weight-bold)',
              color: 'var(--xp-text-inverse)', fontFamily: 'var(--xp-font-display)',
            }}>
              X
            </div>
            <div>
              <div style={{ fontWeight: 'var(--xp-weight-semibold)' }}>XIOPATH</div>
              <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                Autonomous Browser Intelligence Platform — v2.0.0
              </div>
            </div>
          </div>
          <span className="xp-badge xp-badge-purple">Phase R2</span>
        </div>
      </div>
    </div>
  );
}
