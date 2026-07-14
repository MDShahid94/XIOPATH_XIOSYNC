/**
 * XIOPATH — Application Root
 * =============================
 * React Router v7 with nested routes, role-based guards,
 * and global overlays (Command Palette, Toasts).
 */
import React, { useState, useEffect, useCallback, Suspense, lazy } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import useAuthStore from './stores/authStore';
import Shell from './components/layout/Shell';
import CommandPalette from './components/ui/CommandPalette';
import Toast from './components/ui/Toast';

// ─── Code-split all pages via React.lazy ─────────────────────
const LoginPage       = lazy(() => import('./pages/auth/LoginPage'));
const ClientDashboard = lazy(() => import('./pages/client/DashboardPage'));
const ExecutePage     = lazy(() => import('./pages/client/ExecutePage'));
const SessionsPage    = lazy(() => import('./pages/client/SessionsPage'));
const VaultPage       = lazy(() => import('./pages/client/VaultPage'));
const WorkflowsPage   = lazy(() => import('./pages/client/WorkflowsPage'));
const SchedulePage    = lazy(() => import('./pages/client/SchedulePage'));
const MarketplacePage = lazy(() => import('./pages/client/MarketplacePage'));
const AgentsPage      = lazy(() => import('./pages/client/AgentsPage'));
const ActorsPage      = lazy(() => import('./pages/client/ActorsPage'));
const OrgsPage        = lazy(() => import('./pages/client/OrganizationsPage'));
const TypesPage       = lazy(() => import('./pages/client/TypesPage'));
const KnowledgePage   = lazy(() => import('./pages/client/KnowledgePage'));
const SettingsPage    = lazy(() => import('./pages/shared/SettingsPage'));
const AdminDashboard  = lazy(() => import('./pages/admin/DashboardPage'));
const WorkersPage     = lazy(() => import('./pages/admin/WorkersPage'));
const MemoryPage      = lazy(() => import('./pages/admin/MemoryPage'));
const DLQPage         = lazy(() => import('./pages/admin/DLQPage'));
const ConsensusPage   = lazy(() => import('./pages/admin/ConsensusPage'));
const AnalyticsPage   = lazy(() => import('./pages/admin/AnalyticsPage'));
const AuditPage       = lazy(() => import('./pages/admin/AuditPage'));
const DeployPage      = lazy(() => import('./pages/admin/DeployPage'));

// Minimal loading fallback
function LoadingFallback() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '50vh', color: 'var(--xp-text-muted)', gap: '8px',
      fontFamily: 'var(--xp-font-body)', fontSize: 'var(--xp-text-sm)',
    }}>
      <div className="xp-animate-spin" style={{
        width: '20px', height: '20px', border: '2px solid var(--xp-border-subtle)',
        borderTop: '2px solid var(--xp-cyan)', borderRadius: '50%',
      }} />
      Loading...
    </div>
  );
}

// ─── Styles ──────────────────────────────────────────────────
import './styles/tokens.css';
import './styles/components.css';
import './styles/layout.css';
import './styles/animations.css';
import './styles/marketplace.css';
import './styles/agents.css';
import './styles/workflow-studio.css';

/**
 * Protected Route wrapper — redirects to /login if not authenticated
 */
function ProtectedRoute({ children, requiredRole }) {
  const { isAuthenticated, isLoading, user } = useAuthStore();

  if (isLoading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'var(--xp-bg-void)',
      }}>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 'var(--xp-space-4)',
        }}>
          <div style={{
            width: 48,
            height: 48,
            borderRadius: 'var(--xp-radius-xl)',
            background: 'var(--xp-gradient-brand)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 'var(--xp-text-xl)',
            fontWeight: 'var(--xp-weight-bold)',
            color: 'var(--xp-text-inverse)',
            fontFamily: 'var(--xp-font-display)',
          }}>
            X
          </div>
          <span style={{ color: 'var(--xp-text-muted)', fontSize: 'var(--xp-text-sm)' }}>
            Loading XIOPATH...
          </span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && user?.role !== requiredRole) {
    return <Navigate to={user?.role === 'admin' ? '/admin' : '/dashboard'} replace />;
  }

  return children;
}

/**
 * Placeholder page for routes not yet implemented
 */
function ComingSoon({ title }) {
  return (
    <div className="xp-empty xp-animate-fade-in">
      <div style={{
        width: 64,
        height: 64,
        borderRadius: 'var(--xp-radius-xl)',
        background: 'var(--xp-gradient-subtle)',
        border: '1px solid var(--xp-border-default)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '28px',
      }}>
        🚧
      </div>
      <div className="xp-empty-title">{title}</div>
      <div className="xp-empty-desc">
        This page is coming in the next phase. Stay tuned!
      </div>
    </div>
  );
}


export default function App() {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const hydrate = useAuthStore((s) => s.hydrate);

  // Hydrate auth from localStorage on mount
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Global Cmd+K handler
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      }
      if (e.key === 'Escape' && commandPaletteOpen) {
        setCommandPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [commandPaletteOpen]);

  const openPalette = useCallback(() => setCommandPaletteOpen(true), []);
  const closePalette = useCallback(() => setCommandPaletteOpen(false), []);

  return (
    <>
      {/* Global Overlays */}
      <CommandPalette isOpen={commandPaletteOpen} onClose={closePalette} />
      <Toast />

      <Suspense fallback={<LoadingFallback />}>
      <Routes>
        {/* ─── Public Routes ────────────────────────── */}
        <Route path="/login" element={<LoginPage />} />

        {/* ─── Client Routes ────────────────────────── */}
        <Route
          element={
            <ProtectedRoute requiredRole="client">
              <Shell onOpenCommandPalette={openPalette} />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<ClientDashboard />} />
          <Route path="/execute" element={<ExecutePage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/vault" element={<VaultPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/marketplace" element={<MarketplacePage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/actors" element={<ActorsPage />} />
          <Route path="/types" element={<TypesPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/organizations" element={<OrgsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        {/* ─── Admin Routes ─────────────────────────── */}
        <Route
          element={
            <ProtectedRoute requiredRole="admin">
              <Shell onOpenCommandPalette={openPalette} />
            </ProtectedRoute>
          }
        >
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/workers" element={<WorkersPage />} />
          <Route path="/admin/sessions" element={<SessionsPage />} />
          <Route path="/admin/memory" element={<MemoryPage />} />
          <Route path="/admin/dlq" element={<DLQPage />} />
          <Route path="/admin/consensus" element={<ConsensusPage />} />
          <Route path="/admin/analytics" element={<AnalyticsPage />} />
          <Route path="/admin/deploy" element={<DeployPage />} />
          <Route path="/admin/audit" element={<AuditPage />} />
          <Route path="/admin/settings" element={<SettingsPage />} />
        </Route>

        {/* ─── Catch-all ────────────────────────────── */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
      </Suspense>
    </>
  );
}
