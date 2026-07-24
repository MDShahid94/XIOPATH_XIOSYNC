/**
 * One workflow definition in the catalog. A definition is authored as `draft`,
 * promoted to `published` once its spec is a valid DAG (INV-WF-1), and may be
 * `deprecated`. This card is read-only — authoring/publishing are separate,
 * later steps; it surfaces identity, version, and lifecycle state only.
 */
import type { WorkflowSummary } from "@/api/generated/schema";
import { WorkflowStatusBadge } from "@/components/StatusBadge";

interface WorkflowCardProps {
  workflow: WorkflowSummary;
}

export function WorkflowCard({ workflow }: WorkflowCardProps) {
  return (
    <li className="flex flex-col rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-foreground">
            {workflow.name}
          </h3>
          <p className="font-mono text-xs text-muted-foreground">
            v{workflow.version}
          </p>
        </div>
        <WorkflowStatusBadge state={workflow.state} />
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 text-xs">
        <div className="min-w-0">
          <dt className="text-muted-foreground">Workflow ID</dt>
          <dd className="mt-0.5 truncate font-mono text-foreground">
            {workflow.id}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Created by</dt>
          <dd className="mt-0.5 truncate font-mono text-foreground">
            {workflow.created_by}
          </dd>
        </div>
      </dl>
    </li>
  );
}
