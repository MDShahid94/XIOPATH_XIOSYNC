/**
 * Workflows route (doc 04 §2.1, doc 08 §3). Lists the org's workflow
 * definitions with their lifecycle state. Data flows through the single typed
 * client via `useWorkflows`, and the view handles every async state —
 * loading / error / empty / success (INV-FE-6) — via DataState.
 */
import { DataState } from "@/components/DataState";
import { WorkflowCard } from "./WorkflowCard";
import { useWorkflows } from "./useWorkflows";

export default function WorkflowsPage() {
  const { data, status, error, isFetching, refetch } = useWorkflows();
  const workflows = data?.workflows ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Workflows
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          Your organization&apos;s workflow definitions. A workflow is authored
          as a draft and promoted to published once its spec is a valid DAG.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading workflows"
        emptyTitle="No workflows yet"
        emptyMessage="When workflows are defined for your organization, they appear here."
        isEmpty={workflows.length === 0}
      >
        {isFetching && workflows.length > 0 ? (
          <p className="mb-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workflows.map((workflow) => (
            <WorkflowCard key={workflow.id} workflow={workflow} />
          ))}
        </ul>
      </DataState>
    </div>
  );
}
