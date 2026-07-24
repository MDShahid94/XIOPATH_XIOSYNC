/**
 * One worker-pool node as a table row (doc 07 §2). Workers are tabular
 * (host, queue, state, load, heartbeat), so the pool renders as a table.
 * Read-only — draining/retiring a worker is an operational action for a later
 * step.
 */
import type { WorkerSummary } from "@/api/generated/schema";
import { WorkerStatusBadge } from "@/components/StatusBadge";

interface WorkerRowProps {
  worker: WorkerSummary;
}

export function WorkerRow({ worker }: WorkerRowProps) {
  const heartbeat = new Date(worker.last_heartbeat_at);
  const heartbeatLabel = Number.isNaN(heartbeat.getTime())
    ? worker.last_heartbeat_at
    : heartbeat.toLocaleString();

  return (
    <tr className="border-t border-border align-middle">
      <td className="px-4 py-3">
        <span className="font-mono text-xs text-foreground">
          {worker.hostname}
        </span>
      </td>
      <td className="px-4 py-3">
        <WorkerStatusBadge state={worker.state} />
      </td>
      <td className="px-4 py-3">
        <span className="font-mono text-xs text-muted-foreground">
          {worker.queue}
        </span>
      </td>
      <td className="px-4 py-3">
        <span className="font-mono text-xs tabular-nums text-foreground">
          {worker.active_tasks}/{worker.capacity}
        </span>
      </td>
      <td className="hidden whitespace-nowrap px-4 py-3 sm:table-cell">
        <span className="text-xs text-muted-foreground">{heartbeatLabel}</span>
      </td>
    </tr>
  );
}
