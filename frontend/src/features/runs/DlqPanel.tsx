/**
 * Dead-letter queue panel (doc 07 §4, INV-DLQ-1/2/3). A self-contained section
 * with its own four async states (INV-FE-6): it reads the DLQ via
 * `useDeadLetters` and drives the governed propose/resolve transitions via
 * `useDlqGovernance`, invalidating the list after each write so the UI reflects
 * server truth. Nothing here auto-resolves a record.
 */
import { DataState } from "@/components/DataState";
import { toMessage } from "@/lib/problem";
import { DlqCard } from "./DlqCard";
import { useDeadLetters, useDlqGovernance } from "./useRuns";

export function DlqPanel() {
  const deadLetters = useDeadLetters();
  const { propose, resolve } = useDlqGovernance();

  const items = deadLetters.data?.dead_letters ?? [];
  const mutationError = propose.error ?? resolve.error;

  function isBusy(deadLetterId: string): boolean {
    return (
      (propose.isPending && propose.variables?.deadLetterId === deadLetterId) ||
      (resolve.isPending && resolve.variables === deadLetterId)
    );
  }

  return (
    <section aria-label="Dead letter queue" className="mt-10">
      <header className="mb-4">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">
          Dead letter queue
        </h2>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          Failed tasks land here in the open state. Attach a diagnosis to move a
          record into investigation, then resolve it with explicit approval.
        </p>
      </header>

      {mutationError ? (
        <div
          className="mb-4 rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {toMessage(mutationError)}
        </div>
      ) : null}

      <DataState
        status={deadLetters.status}
        error={deadLetters.error}
        onRetry={() => void deadLetters.refetch()}
        loadingLabel="Loading dead-letter records"
        emptyTitle="No dead-letter records"
        emptyMessage="When a task exhausts its retries it lands here for triage."
        isEmpty={items.length === 0}
      >
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {items.map((item) => (
            <DlqCard
              key={item.id}
              item={item}
              busy={isBusy(item.id)}
              onPropose={(deadLetterId, note) =>
                propose.mutate({ deadLetterId, note })
              }
              onResolve={(deadLetterId) => resolve.mutate(deadLetterId)}
            />
          ))}
        </ul>
      </DataState>
    </section>
  );
}
