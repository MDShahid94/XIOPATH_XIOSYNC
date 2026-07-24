/**
 * One capability in the registry. A capability is the typed unit of permission
 * a grant references (INV-CAP-1); this card is read-only and surfaces identity,
 * category, risk tier, and how many active grants reference it.
 */
import type { CapabilitySummary } from "@/api/generated/schema";
import { CapabilityRiskBadge } from "@/components/StatusBadge";

interface CapabilityCardProps {
  capability: CapabilitySummary;
}

export function CapabilityCard({ capability }: CapabilityCardProps) {
  return (
    <li className="flex flex-col rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-foreground">
            {capability.name}
          </h3>
          <p className="text-xs text-muted-foreground">{capability.category}</p>
        </div>
        <CapabilityRiskBadge tier={capability.risk_tier} />
      </div>

      {capability.description ? (
        <p className="mt-3 text-sm text-muted-foreground text-pretty">
          {capability.description}
        </p>
      ) : null}

      <dl className="mt-4 grid grid-cols-1 gap-3 text-xs">
        <div className="min-w-0">
          <dt className="text-muted-foreground">Capability ID</dt>
          <dd className="mt-0.5 truncate font-mono text-foreground">
            {capability.id}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Active grants</dt>
          <dd className="mt-0.5 font-mono tabular-nums text-foreground">
            {capability.grant_count}
          </dd>
        </div>
      </dl>
    </li>
  );
}
