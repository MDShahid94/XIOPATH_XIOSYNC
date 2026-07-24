/**
 * Dashboard route (doc 08 §3: org-scoped summary for any member). Renders the
 * organization's control-plane counters as metric tiles. Data flows through the
 * single typed client via `useDashboardSummary`, and the view handles all four
 * async states — loading / error / empty / success (INV-FE-6) — via DataState.
 */
import { DataState } from "@/components/DataState";
import { useSession } from "@/app/session/useSession";
import { StatCard } from "./StatCard";
import { useDashboardSummary } from "./useDashboardSummary";

export default function DashboardPage() {
  const { session } = useSession();
  const { data, status, error, isFetching, refetch } = useDashboardSummary();

  const generatedAt = data
    ? new Date(data.generated_at).toLocaleString()
    : null;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Org-scoped summary of your control plane.
          {generatedAt ? (
            <span className="ml-1">Updated {generatedAt}.</span>
          ) : null}
        </p>
      </header>

      <section aria-label="Organization summary">
        <DataState
          status={status}
          error={error}
          onRetry={() => void refetch()}
          loadingLabel="Loading summary"
          emptyTitle="No summary available"
          emptyMessage="Once your organization has activity, its metrics appear here."
          isEmpty={!data}
        >
          {data ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              <StatCard label="Actors" value={data.actors} />
              <StatCard label="Capabilities" value={data.capabilities} />
              <StatCard label="Grants" value={data.grants} />
              <StatCard label="Workflows" value={data.workflows} />
              <StatCard
                label="Active runs"
                value={data.runs_active}
                hint={`${data.runs_total} total`}
                accent="primary"
              />
              <StatCard
                label="Events (24h)"
                value={data.events_last_24h}
              />
              <StatCard
                label="Plugins installed"
                value={data.plugins_installed}
                accent="success"
              />
              <StatCard
                label="Workers online"
                value={data.workers_online}
                accent={data.workers_online > 0 ? "success" : "warning"}
              />
            </div>
          ) : null}
        </DataState>
      </section>

      <section aria-label="Active session" className="mt-8">
        <h2 className="mb-3 text-sm font-semibold text-foreground">Session</h2>
        <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
          <div className="bg-card p-4">
            <dt className="text-xs text-muted-foreground">Organization</dt>
            <dd className="mt-1 break-all font-mono text-sm text-foreground">
              {session?.organizationId ?? "—"}
            </dd>
          </div>
          <div className="bg-card p-4">
            <dt className="text-xs text-muted-foreground">Membership role</dt>
            <dd className="mt-1 text-sm text-foreground">
              {session?.membershipRole ?? "—"}
            </dd>
          </div>
          <div className="bg-card p-4">
            <dt className="text-xs text-muted-foreground">Platform role</dt>
            <dd className="mt-1 text-sm text-foreground">
              {session?.platformRole ?? "—"}
            </dd>
          </div>
        </dl>
        {isFetching && data ? (
          <p className="mt-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
      </section>
    </div>
  );
}
