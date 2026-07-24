/**
 * Events route (doc 06 §1, doc 08 §3). Renders the org's append-only
 * audit/activity stream, most recent first. Data flows through the single
 * typed client via `useEvents`, and the view handles every async state —
 * loading / error / empty / success (INV-FE-6) — via DataState.
 */
import { DataState } from "@/components/DataState";
import { EventRow } from "./EventRow";
import { useEvents } from "./useEvents";

export default function EventsPage() {
  const { data, status, error, isFetching, refetch } = useEvents();
  const events = data?.events ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Events
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          The append-only activity stream for your organization. Every
          state-changing action is recorded here for audit.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading events"
        emptyTitle="No events yet"
        emptyMessage="As activity happens in your organization, it appears here."
        isEmpty={events.length === 0}
      >
        {isFetching && events.length > 0 ? (
          <p className="mb-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-left">
            <thead>
              <tr className="text-xs text-muted-foreground">
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium">Severity</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Summary</th>
                <th className="hidden px-4 py-3 font-medium sm:table-cell">
                  Actor
                </th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <EventRow key={event.id} event={event} />
              ))}
            </tbody>
          </table>
        </div>
      </DataState>
    </div>
  );
}
