/**
 * Workers route (doc 07 §2, doc 08 §3). Lists the worker pool that drains the
 * run queue, with each worker's liveness and load. Admin-scoped (the route
 * guard enforces; the server re-checks). Data flows through the single typed
 * client via `useWorkers`, and the view handles every async state —
 * loading / error / empty / success (INV-FE-6) — via DataState.
 */
import { DataState } from "@/components/DataState";
import { WorkerRow } from "./WorkerRow";
import { useWorkers } from "./useWorkers";

export default function WorkersPage() {
  const { data, status, error, isFetching, refetch } = useWorkers();
  const workers = data?.workers ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Workers
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          The worker pool that executes queued tasks. Liveness is derived from
          each worker&apos;s heartbeat; a draining worker finishes in-flight
          tasks but accepts no new ones.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading workers"
        emptyTitle="No workers registered"
        emptyMessage="When workers join your organization's pool, they appear here."
        isEmpty={workers.length === 0}
      >
        {isFetching && workers.length > 0 ? (
          <p className="mb-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-left">
            <thead>
              <tr className="text-xs text-muted-foreground">
                <th className="px-4 py-3 font-medium">Worker</th>
                <th className="px-4 py-3 font-medium">State</th>
                <th className="px-4 py-3 font-medium">Queue</th>
                <th className="px-4 py-3 font-medium">Load</th>
                <th className="hidden px-4 py-3 font-medium sm:table-cell">
                  Last heartbeat
                </th>
              </tr>
            </thead>
            <tbody>
              {workers.map((worker) => (
                <WorkerRow key={worker.id} worker={worker} />
              ))}
            </tbody>
          </table>
        </div>
      </DataState>
    </div>
  );
}
