/**
 * One organization the current actor belongs to (doc 05 §3.1). Surfaces
 * identity, plan, lifecycle state, the caller's role, and member count. The
 * active org is marked so switching context is unambiguous. Read-only.
 */
import type { OrgSummary } from "@/api/generated/schema";
import { OrgStatusBadge, StatusPill } from "@/components/StatusBadge";

interface OrgCardProps {
  org: OrgSummary;
  isActive: boolean;
}

const ROLE_LABEL: Record<OrgSummary["member_role"], string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
  viewer: "Viewer",
};

export function OrgCard({ org, isActive }: OrgCardProps) {
  return (
    <li className="flex flex-col rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-foreground">
            {org.display_name}
          </h3>
          <p className="truncate font-mono text-xs text-muted-foreground">
            {org.slug}
          </p>
        </div>
        <OrgStatusBadge state={org.state} />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <StatusPill tone="neutral">{ROLE_LABEL[org.member_role]}</StatusPill>
        <StatusPill tone={org.plan === "free" ? "neutral" : "success"}>
          {org.plan.charAt(0).toUpperCase() + org.plan.slice(1)}
        </StatusPill>
        {isActive ? <StatusPill tone="success">Active session</StatusPill> : null}
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 text-xs">
        <div className="min-w-0">
          <dt className="text-muted-foreground">Organization ID</dt>
          <dd className="mt-0.5 truncate font-mono text-foreground">
            {org.id}
          </dd>
        </div>
        {typeof org.members_count === "number" ? (
          <div>
            <dt className="text-muted-foreground">Members</dt>
            <dd className="mt-0.5 font-mono tabular-nums text-foreground">
              {org.members_count}
            </dd>
          </div>
        ) : null}
      </dl>
    </li>
  );
}
