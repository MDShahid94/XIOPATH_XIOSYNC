/**
 * XIOPATH — Top Bar
 * ===================
 * Sticky header with breadcrumbs, search trigger, connection status, and user menu.
 */
import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Search, Wifi, WifiOff, ChevronRight, LogOut, User } from 'lucide-react';
import useAuthStore from '../../stores/authStore';
import useWsStore from '../../stores/wsStore';

const ROUTE_LABELS = {
  '/dashboard': 'Dashboard',
  '/execute': 'Execute Agent',
  '/sessions': 'Sessions',
  '/schedule': 'Schedule',
  '/vault': 'Vault',
  '/workflows': 'Workflows',
  '/settings': 'Settings',
  '/admin': 'Overview',
  '/admin/workers': 'Workers',
  '/admin/sessions': 'Sessions',
  '/admin/memory': 'Memory Explorer',
  '/admin/dlq': 'DLQ Triage',
  '/admin/consensus': 'Consensus',
  '/admin/analytics': 'Analytics',
  '/admin/deploy': 'Deploy',
  '/admin/audit': 'Audit Log',
};

export default function Topbar({ onOpenCommandPalette }) {
  const { user, logout, getInitials } = useAuthStore();
  const wsStatus = useWsStore((s) => s.status);
  const navigate = useNavigate();
  const location = useLocation();
  const [showUserMenu, setShowUserMenu] = useState(false);

  // Build breadcrumbs from path
  const pathSegments = location.pathname.split('/').filter(Boolean);
  const breadcrumbs = [];
  const roleLabel = user?.role === 'admin' ? 'Administration' : 'Workspace';
  breadcrumbs.push(roleLabel);

  const currentLabel = ROUTE_LABELS[location.pathname] || pathSegments[pathSegments.length - 1] || 'Home';

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="xp-topbar">
      {/* ─── Left: Breadcrumbs ──────────────────── */}
      <div className="xp-topbar-left">
        <div className="xp-breadcrumbs">
          <span>{roleLabel}</span>
          <ChevronRight size={12} className="xp-breadcrumb-sep" />
          <span className="xp-breadcrumb-current">{currentLabel}</span>
        </div>
      </div>

      {/* ─── Right: Search + Status + User ──────── */}
      <div className="xp-topbar-right">
        {/* Search trigger */}
        <button
          className="xp-search-trigger"
          onClick={onOpenCommandPalette}
        >
          <Search size={14} />
          <span>Search...</span>
          <span className="xp-kbd" style={{ marginLeft: 'auto' }}>⌘K</span>
        </button>

        {/* WebSocket connection status */}
        <div className="xp-connection-status" data-tooltip={`WebSocket: ${wsStatus}`}>
          {wsStatus === 'connected' ? (
            <>
              <span className="xp-dot xp-dot-success xp-dot-pulse" />
              <Wifi size={14} style={{ color: 'var(--xp-success)' }} />
            </>
          ) : (
            <>
              <span className="xp-dot xp-dot-danger" />
              <WifiOff size={14} style={{ color: 'var(--xp-danger)' }} />
            </>
          )}
        </div>

        {/* User menu */}
        <div
          className="xp-user-menu"
          onClick={() => setShowUserMenu(!showUserMenu)}
          style={{ position: 'relative' }}
        >
          <div className="xp-avatar">{getInitials()}</div>
          <span style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-secondary)' }}>
            {user?.username}
          </span>

          {showUserMenu && (
            <div
              style={{
                position: 'absolute',
                top: 'calc(100% + 8px)',
                right: 0,
                background: 'var(--xp-bg-elevated)',
                border: '1px solid var(--xp-border-default)',
                borderRadius: 'var(--xp-radius-lg)',
                padding: 'var(--xp-space-2)',
                minWidth: '180px',
                boxShadow: 'var(--xp-shadow-lg)',
                zIndex: 'var(--xp-z-dropdown)',
              }}
              className="xp-animate-scale-in"
            >
              <div
                style={{
                  padding: 'var(--xp-space-3)',
                  borderBottom: '1px solid var(--xp-border-subtle)',
                  marginBottom: 'var(--xp-space-1)',
                }}
              >
                <div style={{ fontSize: 'var(--xp-text-sm)', fontWeight: 'var(--xp-weight-medium)' }}>
                  {user?.username}
                </div>
                <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', marginTop: '2px' }}>
                  <span className="xp-badge xp-badge-cyan" style={{ textTransform: 'capitalize' }}>
                    {user?.role}
                  </span>
                </div>
              </div>
              <button
                className="xp-nav-item"
                onClick={() => { navigate('/settings'); setShowUserMenu(false); }}
                style={{ width: '100%' }}
              >
                <span className="xp-nav-icon"><User size={16} /></span>
                <span className="xp-nav-label">Profile</span>
              </button>
              <button
                className="xp-nav-item"
                onClick={handleLogout}
                style={{ width: '100%', color: 'var(--xp-danger)' }}
              >
                <span className="xp-nav-icon"><LogOut size={16} /></span>
                <span className="xp-nav-label">Logout</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
