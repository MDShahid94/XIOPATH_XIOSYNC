/**
 * Settings route (doc 05 §3.1, doc 08 §3). Renders the active organization's
 * configuration surface. Admin-scoped (the route guard enforces; the server
 * re-checks). Data flows through the single typed client via `useSettings`,
 * and the view handles every async state — loading / error / empty / success
 * (INV-FE-6) — via DataState. Editing is a governed action for a later step;
 * this page is read-only.
 */
import { DataState } from "@/components/DataState";
import { OrgStatusBadge, StatusPill } from "@/components/StatusBadge";
import { useSettings } from "./useSettings";

export default function SettingsPage() {
  const { data, status, error, isFetching, refetch } = useSettings();

  const updatedLabel = (() => {
    if (!data?.updated_at) return "Never";
    const updated = new Date(data.updated_at);
    return Number.isNaN(updated.getTime())
      ? data.updated_at
      : updated.toLocaleString();
  })();

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Settings
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          Configuration for your active organization. Changes are governed and
          audited; this view is read-only.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading settings"
        emptyTitle="No settings available"
        emptyMessage="Settings for this organization could not be loaded."
        isEmpty={!data}
      >
        {data ? (
          <div className="rounded-lg border border-border bg-card shadow-sm">
            <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
              <div className="min-w-0">
                <h2 className="truncate font-semibold text-foreground">
                  {data.display_name}
                </h2>
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {data.organization_id}
                </p>
              </div>
              <OrgStatusBadge state={data.state} />
            </div>

            <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-b-lg bg-border sm:grid-cols-2">
              <div className="bg-card p-5">
                <dt className="text-xs text-muted-foreground">Plan</dt>
                <dd className="mt-1.5">
                  <StatusPill tone={data.plan === "free" ? "neutral" : "success"}>
                    {data.plan.charAt(0).toUpperCase() + data.plan.slice(1)}
                  </StatusPill>
                </dd>
              </div>
              <div className="bg-card p-5">
                <dt className="text-xs text-muted-foreground">Members</dt>
                <dd className="mt-1.5 font-mono text-sm tabular-nums text-foreground">
                  {data.members_count}
                </dd>
              </div>
              <div className="bg-card p-5">
                <dt className="text-xs text-muted-foreground">Billing email</dt>
                <dd className="mt-1.5 break-all font-mono text-sm text-foreground">
                  {data.billing_email ?? "—"}
                </dd>
              </div>
              <div className="bg-card p-5">
                <dt className="text-xs text-muted-foreground">Last updated</dt>
                <dd className="mt-1.5 text-sm text-foreground">
                  {updatedLabel}
                </dd>
              </div>
            </dl>
          </div>
        ) : null}

        {isFetching && data ? (
          <p className="mt-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
      </DataState>
    </div>
  );
}
