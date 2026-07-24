/**
 * Organizations route (doc 05 §3.1, doc 08 §3). Lists the organizations the
 * current actor belongs to and marks the active session org. Admin-scoped (the
 * route guard enforces; the server re-checks). Data flows through the single
 * typed client via `useOrgs`, and the view handles every async state —
 * loading / error / empty / success (INV-FE-6) — via DataState.
 */
import { DataState } from "@/components/DataState";
import { useSession } from "@/app/session/useSession";
import { OrgCard } from "./OrgCard";
import { useOrgs } from "./useOrgs";

export default function OrgsPage() {
  const { session } = useSession();
  const { data, status, error, isFetching, refetch } = useOrgs();
  const orgs = data?.organizations ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Organizations
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          The organizations you belong to and your role in each. The
          organization backing your current session is marked as active.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading organizations"
        emptyTitle="No organizations"
        emptyMessage="You are not a member of any organization yet."
        isEmpty={orgs.length === 0}
      >
        {isFetching && orgs.length > 0 ? (
          <p className="mb-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {orgs.map((org) => (
            <OrgCard
              key={org.id}
              org={org}
              isActive={org.id === session?.organizationId}
            />
          ))}
        </ul>
      </DataState>
    </div>
  );
}
