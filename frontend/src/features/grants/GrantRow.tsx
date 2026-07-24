/**
 * One grant as a table row (doc 05 §3). A grant binds a capability to a grantee
 * actor; only `active` grants authorize (INV-GRANT-1). Read-only — minting and
 * revoking grants are governed actions for a later step.
 */
import type { GrantSummary } from "@/api/generated/schema";
import { GrantStatusBadge } from "@/components/StatusBadge";

interface GrantRowProps {
  grant: GrantSummary;
}

export function GrantRow({ grant }: GrantRowProps) {
  const expiresLabel = (() => {
    if (!grant.expires_at) return "Never";
    const expires = new Date(grant.expires_at);
    return Number.isNaN(expires.getTime())
      ? grant.expires_at
      : expires.toLocaleDateString();
  })();

  return (
    <tr className="border-t border-border align-middle">
      <td className="px-4 py-3">
        <span className="font-medium text-foreground">
          {grant.capability_name}
        </span>
        <p className="font-mono text-xs text-muted-foreground">
          {grant.capability_id}
        </p>
      </td>
      <td className="px-4 py-3">
        <span className="font-mono text-xs text-foreground">
          {grant.grantee_actor_id}
        </span>
      </td>
      <td className="px-4 py-3">
        <GrantStatusBadge state={grant.state} />
      </td>
      <td className="hidden px-4 py-3 sm:table-cell">
        <span className="font-mono text-xs text-muted-foreground">
          {grant.granted_by}
        </span>
      </td>
      <td className="hidden whitespace-nowrap px-4 py-3 md:table-cell">
        <span className="text-xs text-muted-foreground">{expiresLabel}</span>
      </td>
    </tr>
  );
}
