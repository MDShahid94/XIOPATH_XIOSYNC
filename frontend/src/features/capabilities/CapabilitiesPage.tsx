/**
 * Capabilities route (doc 05 §2, doc 08 §3). Lists the org's capability
 * registry — the typed permission vocabulary grants are minted against. Data
 * flows through the single typed client via `useCapabilities`, and the view
 * handles every async state — loading / error / empty / success (INV-FE-6) —
 * via DataState.
 */
import { DataState } from "@/components/DataState";
import { CapabilityCard } from "./CapabilityCard";
import { useCapabilities } from "./useCapabilities";

export default function CapabilitiesPage() {
  const { data, status, error, isFetching, refetch } = useCapabilities();
  const capabilities = data?.capabilities ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Capabilities
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          The typed permission vocabulary for your organization. Every grant
          binds an actor to one of these capabilities; nothing acts without one.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading capabilities"
        emptyTitle="No capabilities defined"
        emptyMessage="When capabilities are registered for your organization, they appear here."
        isEmpty={capabilities.length === 0}
      >
        {isFetching && capabilities.length > 0 ? (
          <p className="mb-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {capabilities.map((capability) => (
            <CapabilityCard key={capability.id} capability={capability} />
          ))}
        </ul>
      </DataState>
    </div>
  );
}
