/**
 * Runs route (doc 03 §4.4, doc 08 §3). Lists the org's workflow runs with their
 * lifecycle state and embeds the dead-letter queue panel for triage and
 * governed resolution (INV-DLQ-1/2/3). Both sections flow through the single
 * typed client and each handles all four async states independently
 * (INV-FE-6) via DataState.
 */
import { DataState } from "@/components/DataState";
import { DlqPanel } from "./DlqPanel";
import { RunRow } from "./RunRow";
import { useRuns } from "./useRuns";

export default function RunsPage() {
  const { data, status, error, isFetching, refetch } = useRuns();
  const runs = data?.runs ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Runs
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          Executions of your workflows and their current state. Tasks that fail
          terminally are routed to the dead-letter queue below.
        </p>
      </header>

      <section aria-label="Workflow runs">
        <DataState
          status={status}
          error={error}
          onRetry={() => void refetch()}
          loadingLabel="Loading runs"
          emptyTitle="No runs yet"
          emptyMessage="When a workflow is started, its runs appear here."
          isEmpty={runs.length === 0}
        >
          {isFetching && runs.length > 0 ? (
            <p className="mb-3 text-xs text-muted-foreground" role="status">
              Refreshing…
            </p>
          ) : null}
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full text-left">
              <thead>
                <tr className="text-xs text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Run</th>
                  <th className="px-4 py-3 font-medium">Workflow</th>
                  <th className="px-4 py-3 font-medium">State</th>
                  <th className="hidden px-4 py-3 font-medium sm:table-cell">
                    Initiated by
                  </th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <RunRow key={run.id} run={run} />
                ))}
              </tbody>
            </table>
          </div>
        </DataState>
      </section>

      <DlqPanel />
    </div>
  );
}
