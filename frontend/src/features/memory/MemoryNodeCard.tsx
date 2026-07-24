/**
 * One node in the tiered execution-memory graph (doc 09 §2). A node records an
 * intent → action learned for a URL and its promotion tier (candidate →
 * secondary → primary). Read-only; recording/promotion happen elsewhere.
 */
import type { MemoryNodeSummary } from "@/api/generated/schema";
import { MemoryTierBadge } from "@/components/StatusBadge";

interface MemoryNodeCardProps {
  node: MemoryNodeSummary;
}

export function MemoryNodeCard({ node }: MemoryNodeCardProps) {
  const confidencePct = Math.round(
    Math.min(1, Math.max(0, node.confidence)) * 100,
  );
  const updatedAt = new Date(node.updated_at);
  const updatedLabel = Number.isNaN(updatedAt.getTime())
    ? node.updated_at
    : updatedAt.toLocaleString();

  return (
    <li className="flex flex-col rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-foreground">
            {node.intent}
          </h3>
          <p className="truncate text-xs text-muted-foreground">{node.url}</p>
        </div>
        <MemoryTierBadge tier={node.tier} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="text-muted-foreground">Action</dt>
          <dd className="mt-0.5 font-mono text-foreground">
            {node.action_type}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Confidence</dt>
          <dd className="mt-0.5 font-mono tabular-nums text-foreground">
            {confidencePct}%
          </dd>
        </div>
      </dl>

      <p className="mt-4 text-xs text-muted-foreground">
        Updated {updatedLabel}
      </p>
    </li>
  );
}
