/**
 * The three orthogonal authority axes (doc 05 §1.1) — never one overloaded
 * `role` string (H4). Used by the route/permission matrix (INV-FE-4).
 *
 * These checks are UX only. The server re-checks every request against real
 * grants (doc 05 §4); the client never trusts itself for security (doc 08 §3).
 */

export type PlatformRole = "platform_admin" | "none";

export type MembershipRole =
  | "org_owner"
  | "org_admin"
  | "org_member"
  | "org_viewer";

/** Ordered from least to most privileged for `>=` comparisons. */
const MEMBERSHIP_RANK: Record<MembershipRole, number> = {
  org_viewer: 0,
  org_member: 1,
  org_admin: 2,
  org_owner: 3,
};

/** The authority a route demands (doc 08 §3 matrix). */
export interface RouteRequirement {
  /** `"anonymous"` = only signed-out users; `"authenticated"` = any member. */
  access: "anonymous" | "authenticated";
  /** Minimum org membership role, inclusive. */
  minMembershipRole?: MembershipRole;
  /** Require the platform-admin axis (cross-org, audited — doc 05 §3.3). */
  requirePlatformAdmin?: boolean;
}

/** Resolved session authority for the active org (doc 05 §3.1 OrgContext). */
export interface Authority {
  platformRole: PlatformRole;
  membershipRole: MembershipRole;
}

export function meetsMembership(
  role: MembershipRole,
  minimum: MembershipRole,
): boolean {
  return MEMBERSHIP_RANK[role] >= MEMBERSHIP_RANK[minimum];
}

/**
 * Does `authority` satisfy `requirement`? `null` authority means anonymous.
 * Fail-closed: unknown/insufficient authority is denied.
 */
export function satisfies(
  authority: Authority | null,
  requirement: RouteRequirement,
): boolean {
  if (requirement.access === "anonymous") {
    return authority === null;
  }
  // authenticated from here on
  if (authority === null) return false;
  if (requirement.requirePlatformAdmin) {
    return authority.platformRole === "platform_admin";
  }
  if (requirement.minMembershipRole) {
    return meetsMembership(authority.membershipRole, requirement.minMembershipRole);
  }
  return true;
}
