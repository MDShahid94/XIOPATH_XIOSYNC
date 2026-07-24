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
      </Route>
      <Route path="*" element={<Navigate to={ROUTES.dashboard.path} replace />} />
    </Routes>
  );
}
