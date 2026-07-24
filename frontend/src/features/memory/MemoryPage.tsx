/**
 * Memory route (doc 09 §2, doc 08 §3). Lists the org's promoted execution-memory
 * nodes — the intents/actions the memory manager has learned, with their
 * promotion tier. Data flows through the single typed client via `useMemory`,
 * and the view handles every async state — loading / error / empty / success
 * (INV-FE-6) — via DataState.
 */
import { DataState } from "@/components/DataState";
import { MemoryNodeCard } from "./MemoryNodeCard";
import { useMemory } from "./useMemory";

export default function MemoryPage() {
  const { data, status, error, isFetching, refetch } = useMemory();
  const nodes = data?.nodes ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Memory
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          The tiered execution memory for your organization. Learned intents are
          promoted from candidate to org-secondary and finally global-primary as
          confidence accrues.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading memory graph"
        emptyTitle="No memory recorded"
        emptyMessage="As workflows execute and actions are recorded, learned intents appear here."
        isEmpty={nodes.length === 0}
      >
        {isFetching && nodes.length > 0 ? (
          <p className="mb-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {nodes.map((node) => (
            <MemoryNodeCard key={node.id} node={node} />
          ))}
        </ul>
      </DataState>
    </div>
  );
}
