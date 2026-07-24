/**
 * The route guard (doc 08 §3, INV-FE-4). Resolves the current authority from
 * the session and NEVER renders a route the user is not authorized for — it
 * redirects (anonymous → login, authenticated-on-anon-route → dashboard) or
 * shows an authorized-empty state. Client guards are UX only; the server
 * re-checks every request (doc 05 §4). The client never trusts itself.
 */
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { AuthorizedEmptyState } from "@/components/AuthorizedEmptyState";
import { RouteFallback } from "@/components/RouteFallback";
import { satisfies } from "@/lib/authority";
import { useAuthority, useSession } from "@/app/session/useSession";
import type { RouteMeta } from "@/app/routes";
import { ROUTES } from "@/app/routes";

export function RouteGuard({
  route,
  children,
}: {
  route: RouteMeta;
  children: ReactNode;
}) {
  const { status } = useSession();
  const authority = useAuthority();
  const location = useLocation();

  if (status === "authenticating") {
    return <RouteFallback label="Checking your session" />;
  }

  const { requirement } = route;

  // Anonymous-only routes: bounce authenticated users to the dashboard.
  if (requirement.access === "anonymous" && authority !== null) {
    return <Navigate to={ROUTES.dashboard.path} replace />;
  }

  // Authenticated routes: unauthenticated users go to login (preserve intent).
  if (requirement.access === "authenticated" && authority === null) {
    return (
      <Navigate
        to={ROUTES.login.path}
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  // Authenticated but insufficient authority: authorized-empty, not a redirect.
  if (!satisfies(authority, requirement)) {
    return <AuthorizedEmptyState requirement={route.requirementLabel} />;
  }

  return <>{children}</>;
}
