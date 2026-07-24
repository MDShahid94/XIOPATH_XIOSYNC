/**
 * One workflow run as a table row. Runs are inherently tabular (id, parent
 * workflow, state, initiator), so the run list renders as a table for
 * scannability. Read-only: run control (pause/cancel/retry) is a later step.
 */
import type { WorkflowRunSummary } from "@/api/generated/schema";
import { RunStatusBadge } from "@/components/StatusBadge";

interface RunRowProps {
  run: WorkflowRunSummary;
}

export function RunRow({ run }: RunRowProps) {
  return (
    <tr className="border-t border-border">
      <td className="px-4 py-3 align-middle">
        <span className="font-mono text-xs text-foreground">{run.id}</span>
      </td>
      <td className="px-4 py-3 align-middle">
        <span className="font-mono text-xs text-muted-foreground">
          {run.workflow_id}
        </span>
      </td>
      <td className="px-4 py-3 align-middle">
        <RunStatusBadge state={run.state} />
      </td>
      <td className="hidden px-4 py-3 align-middle sm:table-cell">
        <span className="font-mono text-xs text-muted-foreground">
          {run.initiated_by}
        </span>
      </td>
    </tr>
  );
}
