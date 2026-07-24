/**
 * The route / permission matrix (doc 08 §3, INV-FE-4). Every route declares
 * the authority it requires. One canonical entry per concept — no `agents`+
 * `actors` twins (H1), no `_v2` duplicates (M3).
 *
 * Only the foundation routes are wired in Phase 6 Step 1 (`/login`, `/`).
 * The remaining rows are declared here so later steps attach pages to an
 * already-enforced requirement rather than inventing guards ad hoc.
 */
import type { RouteRequirement } from "@/lib/authority";

export interface RouteMeta {
  path: string;
  /** Human label of the required authority, shown in the empty state. */
  requirementLabel: string;
  requirement: RouteRequirement;
}

export const ROUTES = {
  login: {
    path: "/login",
    requirementLabel: "signed-out access",
    requirement: { access: "anonymous" },
  },
  dashboard: {
    path: "/",
    requirementLabel: "organization membership",
    requirement: { access: "authenticated" },
  },
  actors: {
    path: "/actors",
    requirementLabel: "organization membership",
    requirement: { access: "authenticated", minMembershipRole: "org_member" },
  },
  capabilities: {
    path: "/capabilities",
    requirementLabel: "organization membership",
    requirement: { access: "authenticated", minMembershipRole: "org_member" },
  },
  grants: {
    path: "/grants",
    requirementLabel: "organization admin",
    requirement: { access: "authenticated", minMembershipRole: "org_admin" },
  },
  workflows: {
    path: "/workflows",
    requirementLabel: "organization membership",
    requirement: { access: "authenticated", minMembershipRole: "org_member" },
  },
  runs: {
    path: "/runs",
    requirementLabel: "organization membership",
    requirement: { access: "authenticated", minMembershipRole: "org_member" },
  },
  events: {
    path: "/events",
    requirementLabel: "organization membership",
    requirement: { access: "authenticated", minMembershipRole: "org_member" },
  },
  memory: {
    path: "/memory",
    requirementLabel: "organization membership",
    requirement: { access: "authenticated", minMembershipRole: "org_member" },
  },
  workers: {
    path: "/workers",
    requirementLabel: "organization admin",
    requirement: { access: "authenticated", minMembershipRole: "org_admin" },
  },
  orgs: {
    path: "/orgs",
    requirementLabel: "organization owner or admin",
    requirement: { access: "authenticated", minMembershipRole: "org_admin" },
  },
  settings: {
    path: "/settings",
    requirementLabel: "organization owner or admin",
    requirement: { access: "authenticated", minMembershipRole: "org_admin" },
  },
  admin: {
    path: "/admin",
    requirementLabel: "platform administrator",
    requirement: { access: "authenticated", requirePlatformAdmin: true },
  },
} as const satisfies Record<string, RouteMeta>;

export type RouteKey = keyof typeof ROUTES;
