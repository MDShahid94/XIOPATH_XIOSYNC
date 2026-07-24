/**
 * Authenticated app shell (doc 08 §3). Provides the primary navigation and the
 * session/sign-out affordance around the routed content. Chrome renders only
 * when a session exists; for anonymous users it renders the bare outlet so the
 * child route's guard performs the redirect (it never leaks nav to signed-out
 * users, INV-FE-4).
 */
import { NavLink, Outlet } from "react-router-dom";
import { ROUTES } from "@/app/routes";
import { useSession } from "@/app/session/useSession";

interface NavItem {
  to: string;
  label: string;
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: ROUTES.dashboard.path, label: "Dashboard" },
  { to: ROUTES.workflows.path, label: "Workflows" },
  { to: ROUTES.runs.path, label: "Runs" },
  { to: ROUTES.plugins.path, label: "Plugins" },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  const base =
    "block rounded-md px-3 py-2 text-sm font-medium transition-colors";
  return isActive
    ? `${base} bg-primary text-primary-foreground`
    : `${base} text-muted-foreground hover:bg-muted hover:text-foreground`;
}

export function AppLayout() {
  const { session, logout } = useSession();

  if (!session) {
    return <Outlet />;
  }

  return (
    <div className="min-h-screen bg-background md:flex">
      <aside className="border-b border-border bg-card md:h-screen md:w-64 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between gap-2 px-5 py-4 md:block md:py-6">
          <div>
            <p className="text-base font-semibold tracking-tight text-foreground">
              XIOSYNC
            </p>
            <p className="text-xs text-muted-foreground">Control plane</p>
          </div>
        </div>

        <nav
          className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:pb-0"
          aria-label="Primary"
        >
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === ROUTES.dashboard.path}
              className={navLinkClass}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-border bg-card px-5 py-3">
          <div className="min-w-0">
            <p className="truncate text-xs text-muted-foreground">
              Organization
            </p>
            <p className="truncate font-mono text-sm text-foreground">
              {session.organizationId}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground sm:inline-flex">
              {session.membershipRole}
            </span>
            <button
              type="button"
              onClick={() => void logout()}
              className="rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              Sign out
            </button>
          </div>
        </header>

        <main className="flex-1 px-5 py-6 md:px-8 md:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
