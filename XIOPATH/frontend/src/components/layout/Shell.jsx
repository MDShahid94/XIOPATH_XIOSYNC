/**
 * XIOPATH — App Shell
 * =====================
 * Wraps the authenticated app with Sidebar + Topbar + Main content area.
 */
import React, { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import useWsStore from '../../stores/wsStore';

export default function Shell({ onOpenCommandPalette }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('xp_sidebar_collapsed') === 'true';
  });
  const connect = useWsStore((s) => s.connect);
  const disconnect = useWsStore((s) => s.disconnect);

  // Persist sidebar state
  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      localStorage.setItem('xp_sidebar_collapsed', String(!prev));
      return !prev;
    });
  };

  // Connect WebSocket on mount
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return (
    <div className="xp-shell">
      <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Topbar onOpenCommandPalette={onOpenCommandPalette} />

        <main
          className="xp-main"
          style={{
            marginLeft: sidebarCollapsed ? 'var(--xp-sidebar-collapsed)' : 'var(--xp-sidebar-width)',
          }}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
