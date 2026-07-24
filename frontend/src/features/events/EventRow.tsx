/**
 * One event as a table row. The event stream is inherently tabular (time,
 * type, severity, actor, summary), so it renders as a table for scannability.
 * Read-only — the stream is append-only (doc 06 §1).
 */
import type { EventSummary } from "@/api/generated/schema";
import { EventSeverityBadge } from "@/components/StatusBadge";

interface EventRowProps {
  event: EventSummary;
}

export function EventRow({ event }: EventRowProps) {
  const occurredAt = new Date(event.occurred_at);
  const occurredLabel = Number.isNaN(occurredAt.getTime())
    ? event.occurred_at
    : occurredAt.toLocaleString();

  return (
    <tr className="border-t border-border align-top">
      <td className="whitespace-nowrap px-4 py-3">
        <span className="text-xs text-muted-foreground">{occurredLabel}</span>
      </td>
      <td className="px-4 py-3">
        <EventSeverityBadge severity={event.severity} />
      </td>
      <td className="px-4 py-3">
        <span className="font-mono text-xs text-foreground">{event.type}</span>
      </td>
      <td className="px-4 py-3">
        <p className="text-sm text-foreground text-pretty">{event.summary}</p>
        {event.resource ? (
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">
            {event.resource}
          </p>
        ) : null}
      </td>
      <td className="hidden px-4 py-3 sm:table-cell">
        <span className="font-mono text-xs text-muted-foreground">
          {event.actor_id ?? "—"}
        </span>
      </td>
    </tr>
  );
}
