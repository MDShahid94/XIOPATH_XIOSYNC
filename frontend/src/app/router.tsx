/**
 * Application router. Route-level code splitting via `React.lazy` (doc 08 §8),
 * each route wrapped in its own error boundary (doc 08 §5) and the authority
 * guard (INV-FE-4). Only the foundation routes are mounted in Phase 6 Step 1.
 */
import {
  lazy,
  Suspense,
  type ComponentType,
  type ReactElement,
} from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { RouteFallback } from "@/components/RouteFallback";
import { RouteGuard } from "@/app/guards/RouteGuard";
import { AppLayout } from "@/app/layout/AppLayout";
import { ROUTES, type RouteMeta } from "@/app/routes";

const LoginPage = lazy(() => import("@/features/auth/LoginPage"));
const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage"));
const PluginsPage = lazy(() => import("@/features/plugins/PluginsPage"));
const WorkflowsPage = lazy(
  () => import("@/features/workflows/WorkflowsPage"),
);
const RunsPage = lazy(() => import("@/features/runs/RunsPage"));
const CapabilitiesPage = lazy(
  () => import("@/features/capabilities/CapabilitiesPage"),
);
const EventsPage = lazy(() => import("@/features/events/EventsPage"));
const MemoryPage = lazy(() => import("@/features/memory/MemoryPage"));
const WorkersPage = lazy(() => import("@/features/workers/WorkersPage"));
const GrantsPage = lazy(() => import("@/features/grants/GrantsPage"));
const OrgsPage = lazy(() => import("@/features/orgs/OrgsPage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const AdminPage = lazy(() => import("@/features/admin/AdminPage"));

function guarded(
  route: RouteMeta,
  Page: ComponentType,
  area: string,
): ReactElement {
  return (
    <ErrorBoundary area={area}>
      <Suspense fallback={<RouteFallback />}>
        <RouteGuard route={route}>
          <Page />
        </RouteGuard>
      </Suspense>
    </ErrorBoundary>
  );
}

export function AppRouter() {
  return (
    <Routes>
      <Route
        path={ROUTES.login.path}
        element={guarded(ROUTES.login, LoginPage, "sign in")}
      />
      <Route element={<AppLayout />}>
        <Route
          path={ROUTES.dashboard.path}
          element={guarded(ROUTES.dashboard, DashboardPage, "dashboard")}
        />
        <Route
          path={ROUTES.plugins.path}
          element={guarded(ROUTES.plugins, PluginsPage, "plugins")}
        />
        <Route
          path={ROUTES.workflows.path}
          element={guarded(ROUTES.workflows, WorkflowsPage, "workflows")}
        />
        <Route
          path={ROUTES.runs.path}
          element={guarded(ROUTES.runs, RunsPage, "runs")}
        />
        <Route
          path={ROUTES.capabilities.path}
          element={guarded(
            ROUTES.capabilities,
            CapabilitiesPage,
            "capabilities",
          )}
        />
        <Route
          path={ROUTES.events.path}
          element={guarded(ROUTES.events, EventsPage, "events")}
        />
        <Route
          path={ROUTES.memory.path}
          element={guarded(ROUTES.memory, MemoryPage, "memory")}
        />
        <Route
          path={ROUTES.workers.path}
          element={guarded(ROUTES.workers, WorkersPage, "workers")}
        />
        <Route
          path={ROUTES.grants.path}
          element={guarded(ROUTES.grants, GrantsPage, "grants")}
        />
        <Route
          path={ROUTES.orgs.path}
          element={guarded(ROUTES.orgs, OrgsPage, "organizations")}
        />
        <Route
          path={ROUTES.settings.path}
          element={guarded(ROUTES.settings, SettingsPage, "settings")}
        />
        <Route
          path={ROUTES.admin.path}
          element={guarded(ROUTES.admin, AdminPage, "admin")}
        />
      </Route>
      <Route path="*" element={<Navigate to={ROUTES.dashboard.path} replace />} />
    </Routes>
  );
}
