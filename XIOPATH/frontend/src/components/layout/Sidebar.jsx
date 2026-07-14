/**
 * XIOPATH — Sidebar Navigation
 * ===============================
 * Collapsible sidebar with role-based navigation groups.
 * Matches the xp-sidebar CSS classes from layout.css.
 */
import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Play, History, KeyRound, Calendar,
  Network, AlertOctagon, ShieldCheck, BarChart3, FileText,
  Server, Settings, PanelLeftClose, PanelLeftOpen,
  Cpu, Globe, Search, Store, Bot, Building, Users, Tags
} from 'lucide-react';
import useAuthStore from '../../stores/authStore';

const CLIENT_NAV = [
  {
    title: 'Operations',
    items: [
      { label: 'Dashboard', icon: LayoutDashboard, path: '/dashboard' },
      { label: 'Execute Agent', icon: Play, path: '/execute' },
      { label: 'Sessions', icon: History, path: '/sessions' },
      { label: 'Schedule', icon: Calendar, path: '/schedule' },
    ],
  },
  {
    title: 'Resources',
    items: [
      { label: 'Actors', icon: Users, path: '/actors' },
      { label: 'Types', icon: Tags, path: '/types' },
      { label: 'Organizations', icon: Building, path: '/organizations' },
      { label: 'Vault', icon: KeyRound, path: '/vault' },
      { label: 'Knowledge', icon: Search, path: '/knowledge' },
      { label: 'Workflows', icon: Network, path: '/workflows' },
      { label: 'Marketplace', icon: Store, path: '/marketplace' },
    ],
  },
];

const ADMIN_NAV = [
  {
    title: 'Monitoring',
    items: [
      { label: 'Overview', icon: LayoutDashboard, path: '/admin' },
      { label: 'Workers', icon: Server, path: '/admin/workers' },
      { label: 'Sessions', icon: History, path: '/admin/sessions' },
    ],
  },
  {
    title: 'Intelligence',
    items: [
      { label: 'Memory Explorer', icon: Search, path: '/admin/memory' },
      { label: 'DLQ Triage', icon: AlertOctagon, path: '/admin/dlq' },
      { label: 'Consensus', icon: ShieldCheck, path: '/admin/consensus' },
    ],
  },
  {
    title: 'Management',
    items: [
      { label: 'Analytics', icon: BarChart3, path: '/admin/analytics' },
      { label: 'Deploy', icon: Cpu, path: '/admin/deploy' },
      { label: 'Audit Log', icon: FileText, path: '/admin/audit' },
    ],
  },
];

export default function Sidebar({ collapsed, onToggle }) {
  const { user, logout, getInitials } = useAuthStore();
  const location = useLocation();

  const navSections = user?.role === 'admin' ? ADMIN_NAV : CLIENT_NAV;

  return (
    <aside className={`xp-sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* ─── Header / Logo ─────────────────────────── */}
      <div className="xp-sidebar-header">
        <div className="xp-sidebar-logo">X</div>
        <span className="xp-sidebar-brand">XIOPATH</span>
      </div>

      {/* ─── Navigation ────────────────────────────── */}
      <nav className="xp-sidebar-nav">
        {navSections.map((section) => (
          <div key={section.title} className="xp-sidebar-section">
            <div className="xp-sidebar-section-title">{section.title}</div>
            {section.items.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path ||
                (item.path !== '/dashboard' && item.path !== '/admin' && location.pathname.startsWith(item.path));

              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={`xp-nav-item ${isActive ? 'active' : ''}`}
                  data-tooltip={collapsed ? item.label : undefined}
                >
                  <span className="xp-nav-icon"><Icon /></span>
                  <span className="xp-nav-label">{item.label}</span>
                  {item.badge && (
                    <span className="xp-nav-badge">{item.badge}</span>
                  )}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>

      {/* ─── Footer ────────────────────────────────── */}
      <div className="xp-sidebar-footer">
        <NavLink
          to="/settings"
          className={`xp-nav-item ${location.pathname === '/settings' ? 'active' : ''}`}
        >
          <span className="xp-nav-icon"><Settings /></span>
          <span className="xp-nav-label">Settings</span>
        </NavLink>

        <button
          className="xp-nav-item"
          onClick={onToggle}
          data-tooltip={collapsed ? 'Expand' : undefined}
        >
          <span className="xp-nav-icon">
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </span>
          <span className="xp-nav-label">
            {collapsed ? 'Expand' : 'Collapse'}
          </span>
        </button>
      </div>
    </aside>
  );
}
