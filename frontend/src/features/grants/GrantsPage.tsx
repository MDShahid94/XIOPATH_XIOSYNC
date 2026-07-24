/**
 * Grants route (doc 05 §3, doc 08 §3). Lists the org's capability grants — the
 * capability→actor bindings that authorize action. Admin-scoped (the route
 * guard enforces; the server re-checks). Data flows through the single typed
 * client via `useGrants`, and the view handles every async state —
 * loading / error / empty / success (INV-FE-6) — via DataState.
 */
import { DataState } from "@/components/DataState";
import { GrantRow } from "./GrantRow";
import { useGrants } from "./useGrants";

export default function GrantsPage() {
  const { data, status, error, isFetching, refetch } = useGrants();
  const grants = data?.grants ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Grants
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          Capability grants issued to actors in your organization. Only active
          grants authorize; suspended, revoked, and expired grants are inert.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading grants"
        emptyTitle="No grants issued"
        emptyMessage="When capabilities are granted to actors, those grants appear here."
        isEmpty={grants.length === 0}
      >
        {isFetching && grants.length > 0 ? (
          <p className="mb-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-left">
            <thead>
              <tr className="text-xs text-muted-foreground">
                <th className="px-4 py-3 font-medium">Capability</th>
                <th className="px-4 py-3 font-medium">Grantee</th>
                <th className="px-4 py-3 font-medium">State</th>
                <th className="hidden px-4 py-3 font-medium sm:table-cell">
                  Granted by
                </th>
                <th className="hidden px-4 py-3 font-medium md:table-cell">
                  Expires
                </th>
              </tr>
            </thead>
            <tbody>
              {grants.map((grant) => (
                <GrantRow key={grant.id} grant={grant} />
              ))}
            </tbody>
          </table>
        </div>
      </DataState>
    </div>
  );
}
