/**
 * Authenticated app shell (doc 08 §3). Provides the primary navigation and the
 * session/sign-out affordance around the routed content. Chrome renders only
 * when a session exists; for anonymous users it renders the bare outlet so the
 * child route's guard performs the redirect (it never leaks nav to signed-out
 * users, INV-FE-4).
 */
import { NavLink, Outlet } from "react-router-dom";
import { ROUTES, type RouteMeta } from "@/app/routes";
import { satisfies } from "@/lib/authority";
import { useAuthority, useSession } from "@/app/session/useSession";

interface NavItem {
  route: RouteMeta;
  label: string;
}

interface NavSection {
  heading: string;
  items: readonly NavItem[];
}

/**
 * Navigation grouped by concern. Each item carries its route's authority
 * requirement so the shell can hide links the current authority cannot satisfy
 * — the guard still fail-closes on direct navigation (INV-FE-4), this is UX.
 */
const NAV_SECTIONS: readonly NavSection[] = [
  {
    heading: "Overview",
    items: [{ route: ROUTES.dashboard, label: "Dashboard" }],
  },
  {
    heading: "Execution",
    items: [
      { route: ROUTES.workflows, label: "Workflows" },
      { route: ROUTES.runs, label: "Runs" },
      { route: ROUTES.workers, label: "Workers" },
    ],
  },
  {
    heading: "Authorization",
    items: [
      { route: ROUTES.capabilities, label: "Capabilities" },
      { route: ROUTES.grants, label: "Grants" },
      { route: ROUTES.plugins, label: "Plugins" },
    ],
  },
  {
    heading: "Observability",
    items: [
      { route: ROUTES.events, label: "Events" },
      { route: ROUTES.memory, label: "Memory" },
    ],
  },
  {
    heading: "Administration",
    items: [
      { route: ROUTES.orgs, label: "Organizations" },
      { route: ROUTES.settings, label: "Settings" },
      { route: ROUTES.admin, label: "Admin" },
    ],
  },
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
  const authority = useAuthority();

  if (!session) {
    return <Outlet />;
  }

  const visibleSections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) =>
      satisfies(authority, item.route.requirement),
    ),
  })).filter((section) => section.items.length > 0);

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
          className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:gap-4 md:overflow-visible md:pb-6"
          aria-label="Primary"
        >
          {visibleSections.map((section) => (
            <div key={section.heading} className="flex gap-1 md:flex-col md:gap-1">
              <p className="hidden px-3 py-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground md:block">
                {section.heading}
              </p>
              {section.items.map((item) => (
                <NavLink
                  key={item.route.path}
                  to={item.route.path}
                  end={item.route.path === ROUTES.dashboard.path}
                  className={navLinkClass}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
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
