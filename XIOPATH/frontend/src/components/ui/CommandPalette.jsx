/**
 * XIOPATH — Command Palette (Cmd+K)
 * ====================================
 * Quick search and navigation overlay.
 * Keyboard-first: type to filter, arrow keys to navigate, Enter to select.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ModalPortal from '../ModalPortal';
import {
  Search, LayoutDashboard, Play, History, KeyRound, Calendar,
  Network, AlertOctagon, ShieldCheck, BarChart3, FileText,
  Server, Settings, Cpu, LogOut, X
} from 'lucide-react';
import useAuthStore from '../../stores/authStore';

const ALL_COMMANDS = [
  // Client pages
  { id: 'dashboard', label: 'Go to Dashboard', icon: LayoutDashboard, path: '/dashboard', roles: ['client'] },
  { id: 'execute', label: 'Execute Agent', icon: Play, path: '/execute', roles: ['client'] },
  { id: 'sessions', label: 'View Sessions', icon: History, path: '/sessions', roles: ['client'] },
  { id: 'schedule', label: 'Schedule Workflows', icon: Calendar, path: '/schedule', roles: ['client'] },
  { id: 'vault', label: 'Open Vault', icon: KeyRound, path: '/vault', roles: ['client'] },
  { id: 'workflows', label: 'Browse Workflows', icon: Network, path: '/workflows', roles: ['client'] },
  // Admin pages
  { id: 'admin-overview', label: 'Admin Overview', icon: LayoutDashboard, path: '/admin', roles: ['admin'] },
  { id: 'admin-workers', label: 'Worker Management', icon: Server, path: '/admin/workers', roles: ['admin'] },
  { id: 'admin-memory', label: 'Memory Explorer', icon: Search, path: '/admin/memory', roles: ['admin'] },
  { id: 'admin-dlq', label: 'DLQ Triage', icon: AlertOctagon, path: '/admin/dlq', roles: ['admin'] },
  { id: 'admin-consensus', label: 'Consensus Dashboard', icon: ShieldCheck, path: '/admin/consensus', roles: ['admin'] },
  { id: 'admin-analytics', label: 'Analytics', icon: BarChart3, path: '/admin/analytics', roles: ['admin'] },
  { id: 'admin-deploy', label: 'Deploy Workers', icon: Cpu, path: '/admin/deploy', roles: ['admin'] },
  { id: 'admin-audit', label: 'Audit Log', icon: FileText, path: '/admin/audit', roles: ['admin'] },
  // Shared
  { id: 'settings', label: 'Settings', icon: Settings, path: '/settings', roles: ['client', 'admin'] },
  { id: 'logout', label: 'Logout', icon: LogOut, action: 'logout', roles: ['client', 'admin'] },
];

export default function CommandPalette({ isOpen, onClose }) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  // Filter commands by role and query
  const filtered = ALL_COMMANDS.filter((cmd) => {
    if (!cmd.roles.includes(user?.role)) return false;
    if (!query) return true;
    return cmd.label.toLowerCase().includes(query.toLowerCase());
  });

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Keyboard handler
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && filtered[selectedIndex]) {
      e.preventDefault();
      executeCommand(filtered[selectedIndex]);
    } else if (e.key === 'Escape') {
      onClose();
    }
  }, [filtered, selectedIndex, onClose]);

  const executeCommand = (cmd) => {
    if (cmd.action === 'logout') {
      logout();
      navigate('/login');
    } else if (cmd.path) {
      navigate(cmd.path);
    }
    onClose();
  };

  if (!isOpen) return null;

  return (
    <ModalPortal>
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '15vh'
      }}>
        {/* Backdrop */}
        <div
          onClick={onClose}
          style={{
            position: 'absolute',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.6)',
            backdropFilter: 'blur(4px)',
          }}
          className="xp-animate-fade-in"
        />

        {/* Palette */}
        <div
          style={{
            position: 'relative',
            width: '100%',
            maxWidth: '560px',
            background: 'var(--xp-bg-elevated)',
            border: '1px solid var(--xp-border-default)',
            borderRadius: 'var(--xp-radius-xl)',
            boxShadow: 'var(--xp-shadow-xl)',
            overflow: 'hidden',
          }}
          className="xp-animate-scale-in"
          onKeyDown={handleKeyDown}
        >
        {/* Search input */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--xp-space-3)',
          padding: 'var(--xp-space-4)',
          borderBottom: '1px solid var(--xp-border-subtle)',
        }}>
          <Search size={18} style={{ color: 'var(--xp-text-muted)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command or search..."
            style={{
              flex: 1,
              background: 'none',
              border: 'none',
              outline: 'none',
              color: 'var(--xp-text-primary)',
              fontSize: 'var(--xp-text-md)',
              fontFamily: 'var(--xp-font-body)',
            }}
          />
          <button
            onClick={onClose}
            className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm"
          >
            <X size={16} />
          </button>
        </div>

        {/* Results */}
        <div style={{
          maxHeight: '320px',
          overflowY: 'auto',
          padding: 'var(--xp-space-2)',
        }}>
          {filtered.length === 0 ? (
            <div style={{
              padding: 'var(--xp-space-8)',
              textAlign: 'center',
              color: 'var(--xp-text-muted)',
              fontSize: 'var(--xp-text-sm)',
            }}>
              No results found for "{query}"
            </div>
          ) : (
            filtered.map((cmd, i) => {
              const Icon = cmd.icon;
              const isSelected = i === selectedIndex;
              return (
                <button
                  key={cmd.id}
                  onClick={() => executeCommand(cmd)}
                  onMouseEnter={() => setSelectedIndex(i)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--xp-space-3)',
                    width: '100%',
                    padding: 'var(--xp-space-3) var(--xp-space-3)',
                    background: isSelected ? 'rgba(255, 255, 255, 0.06)' : 'transparent',
                    border: 'none',
                    borderRadius: 'var(--xp-radius-md)',
                    color: isSelected ? 'var(--xp-text-primary)' : 'var(--xp-text-secondary)',
                    fontSize: 'var(--xp-text-sm)',
                    fontFamily: 'var(--xp-font-body)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 100ms ease',
                  }}
                >
                  <Icon size={16} style={{
                    color: isSelected ? 'var(--xp-cyan)' : 'var(--xp-text-muted)',
                    flexShrink: 0,
                  }} />
                  <span style={{ flex: 1 }}>{cmd.label}</span>
                  {isSelected && (
                    <span className="xp-kbd" style={{ fontSize: '10px' }}>↵</span>
                  )}
                </button>
              );
            })
          )}
        </div>

        {/* Footer hint */}
        <div style={{
          padding: 'var(--xp-space-2) var(--xp-space-4)',
          borderTop: '1px solid var(--xp-border-subtle)',
          display: 'flex',
          gap: 'var(--xp-space-4)',
          fontSize: 'var(--xp-text-xs)',
          color: 'var(--xp-text-muted)',
        }}>
          <span><span className="xp-kbd">↑↓</span> Navigate</span>
          <span><span className="xp-kbd">↵</span> Select</span>
          <span><span className="xp-kbd">Esc</span> Close</span>
        </div>
      </div>
      </div>
    </ModalPortal>
  );
}
