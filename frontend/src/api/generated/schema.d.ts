/**
 * GENERATED CONTRACT TYPES — DO NOT EDIT BY HAND.
 *
 * Placeholder stub for Phase 6 Step 1. This file will be overwritten by
 * `pnpm gen:api` (openapi-typescript) once the FastAPI OpenAPI schema is
 * exported in CI (doc 04 §2.3, doc 08 §1). The shapes below mirror
 * `xiosync/api/routers/auth.py` so the transport layer type-checks today.
 */

/** RFC 9457 `application/problem+json` body emitted by the API (doc 04 §2.3). */
export interface Problem {
  type: string;
  title: string;
  status: number;
  code: string;
  request_id: string;
  detail?: string;
}

/** `POST /auth/login` request body. */
export interface LoginRequest {
  organization_id: string;
  email: string;
  password: string;
}

/** `POST /auth/refresh` request body. */
export interface RefreshRequest {
  refresh_token: string;
}

/** Token payload returned by `/auth/login` and `/auth/refresh`. */
export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  access_token_expires_at: string;
  refresh_token: string;
  session_id: string;
  organization_id: string;
  request_id: string;
}

/** `POST /auth/logout` response body. */
export interface LogoutResponse {
  status: "logged_out";
  request_id: string;
}

/* ------------------------------------------------------------------------- *
 * Dashboard (doc 08 §3: org-scoped summary for any member).
 * ------------------------------------------------------------------------- */

/** Org-scoped counters rendered by the dashboard summary widgets. */
export interface DashboardSummary {
  organization_id: string;
  actors: number;
  capabilities: number;
  grants: number;
  workflows: number;
  runs_active: number;
  runs_total: number;
  events_last_24h: number;
  plugins_installed: number;
  workers_online: number;
  /** ISO-8601 timestamp the counters were computed at. */
  generated_at: string;
}

/* ------------------------------------------------------------------------- *
 * Sandboxed plugins (doc 07 §5, INV-PLUGIN-1..4). Mirrors
 * `xiosync/api/routers/plugins.py`.
 * ------------------------------------------------------------------------- */

/** A plugin manifest's lifecycle state. */
export type PluginState = "registered" | "deprecated";

/** Read-model for one registered plugin in the org catalog. */
export interface PluginSummary {
  id: string;
  name: string;
  version: string;
  description?: string;
  state: PluginState;
  /** Capability whose grant authorizes the plugin (INV-PLUGIN-1). */
  required_capability: string;
  /** Number of typed RPC methods the manifest declares (INV-PLUGIN-2). */
  rpc_method_count: number;
  /** Size of the network allowlist; 0 = deny-all (INV-PLUGIN-4). */
  network_allowlist_size: number;
}

/** `GET /plugins` response body. */
export interface PluginCatalogResponse {
  plugins: PluginSummary[];
  total: number;
}

/**
 * Installation lifecycle (INV-PLUGIN-3: approval-gated). A fresh install lands
 * in `pending_approval`; reaching `active` requires separate approve + activate.
 */
export type InstallationState =
  | "pending_approval"
  | "approved"
  | "active"
  | "suspended"
  | "revoked";

/** Read-model for a `plugin_installations` row (INV-PLUGIN-3). */
export interface InstallationResponse {
  id: string;
  organization_id: string;
  plugin_id: string;
  state: InstallationState;
  requested_by: string;
  approved_by?: string | null;
  grant_id?: string | null;
}

/** `GET /plugins/installations` response body. */
export interface InstallationsResponse {
  installations: InstallationResponse[];
  total: number;
}

/** `POST /plugins/{plugin_id}/install` request body (INV-PLUGIN-3). */
export interface InstallRequest {
  requested_by: string;
}

/** `POST /plugins/installations/{installation_id}/approve` request body. */
export interface ApproveRequest {
  approved_by: string;
}

/* ------------------------------------------------------------------------- *
 * Durable-execution spine (doc 04 §2.1, doc 07 §1/§4). Mirrors
 * `xiosync/services/workflows.py` records and `xiosync/api/routers/dlq.py`.
 * The list reads below are the org-scoped control-plane reads the OpenAPI
 * generator will formalize; DLQ propose/resolve mirror the mounted router
 * exactly (INV-DLQ-2/3).
 * ------------------------------------------------------------------------- */

/** A workflow definition's lifecycle state (domain/workflows.py). */
export type WorkflowState = "draft" | "published" | "deprecated";

/** Read-model for one `workflows` row. */
export interface WorkflowSummary {
  id: string;
  organization_id: string;
  name: string;
  version: number;
  state: WorkflowState;
  created_by: string;
}

/** `GET /workflows` response body. */
export interface WorkflowsResponse {
  workflows: WorkflowSummary[];
  total: number;
}

/** A workflow run's lifecycle state (doc 03 §4.4). */
export type WorkflowRunState =
  | "queued"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "cancelled";

/** Read-model for one `workflow_runs` row. */
export interface WorkflowRunSummary {
  id: string;
  organization_id: string;
  workflow_id: string;
  state: WorkflowRunState;
  initiated_by: string;
}

/** `GET /runs` response body. */
export interface RunsResponse {
  runs: WorkflowRunSummary[];
  total: number;
}

/**
 * Dead-letter lifecycle (INV-DLQ-1/2/3): a failed task lands `open`; a
 * governed `propose` advances it to `investigating`; an explicitly approved
 * `resolve` closes it as `resolved`. Nothing auto-resolves.
 */
export type DeadLetterState = "open" | "investigating" | "resolved";

/** Read-model for a `dead_letters` row (mirrors dlq.py DeadLetterResponse). */
export interface DeadLetterResponse {
  id: string;
  organization_id: string;
  task_id: string;
  state: DeadLetterState;
  failure_reason?: string | null;
  proposal_id?: string | null;
  diagnosis?: Record<string, unknown> | null;
}

/** `GET /dlq` response body. */
export interface DeadLettersResponse {
  dead_letters: DeadLetterResponse[];
  total: number;
}

/** `POST /dlq/{dead_letter_id}/propose` request body (INV-DLQ-2). */
export interface ProposeRequest {
  /** Advisory, machine-readable diagnosis; never mutates the live spec. */
  diagnosis: Record<string, unknown>;
}

/** `POST /dlq/{dead_letter_id}/propose` response body. */
export interface ProposeResponse {
  dead_letter_id: string;
  proposal_id: string;
  state: "investigating";
}

/** `POST /dlq/{dead_letter_id}/resolve` request body (INV-DLQ-3). */
export interface ResolveRequest {
  /** Must be `true`; auto-resolution is forbidden (INV-DLQ-3). */
  explicit_approval: boolean;
}

/** `POST /dlq/{dead_letter_id}/resolve` response body. */
export interface ResolveResponse {
  dead_letter_id: string;
  state: "resolved";
}

/* ------------------------------------------------------------------------- *
 * Capabilities (doc 05 §2, INV-CAP-1). The typed permission vocabulary a grant
 * can reference. Org-scoped read model.
 * ------------------------------------------------------------------------- */

/** How much blast radius exercising a capability carries. */
export type CapabilityRiskTier = "low" | "medium" | "high";

/** Read-model for one `capabilities` row. */
export interface CapabilitySummary {
  id: string;
  organization_id: string;
  name: string;
  description?: string | null;
  category: string;
  risk_tier: CapabilityRiskTier;
  /** Number of active grants referencing this capability (INV-CAP-1). */
  grant_count: number;
}

/** `GET /capabilities` response body. */
export interface CapabilitiesResponse {
  capabilities: CapabilitySummary[];
  total: number;
}

/* ------------------------------------------------------------------------- *
 * Grants (doc 05 §3, INV-GRANT-1/2). A grant binds a capability to a grantee
 * actor; only active grants authorize. Admin-scoped read model.
 * ------------------------------------------------------------------------- */

/** Grant lifecycle. Only `active` authorizes; the rest are inert. */
export type GrantState = "active" | "suspended" | "revoked" | "expired";

/** Read-model for one `grants` row. */
export interface GrantSummary {
  id: string;
  organization_id: string;
  capability_id: string;
  capability_name: string;
  grantee_actor_id: string;
  state: GrantState;
  granted_by: string;
  /** ISO-8601 expiry, or null for a non-expiring grant. */
  expires_at?: string | null;
}

/** `GET /grants` response body. */
export interface GrantsResponse {
  grants: GrantSummary[];
  total: number;
}

/* ------------------------------------------------------------------------- *
 * Events (doc 06 §1). The append-only audit/activity stream. Org-scoped read.
 * ------------------------------------------------------------------------- */

/** Severity of an event, mapped onto the status accent tokens. */
export type EventSeverity = "info" | "warning" | "error";

/** Read-model for one `events` row. */
export interface EventSummary {
  id: string;
  organization_id: string;
  type: string;
  severity: EventSeverity;
  actor_id?: string | null;
  resource?: string | null;
  summary: string;
  /** ISO-8601 timestamp the event was recorded at. */
  occurred_at: string;
}

/** `GET /events` response body. */
export interface EventsResponse {
  events: EventSummary[];
  total: number;
}

/* ------------------------------------------------------------------------- *
 * Memory (doc 09 §2). The tiered execution-memory graph. Org-scoped read of
 * the promoted intents/actions the memory manager exposes.
 * ------------------------------------------------------------------------- */

/**
 * Promotion tier of a memory node: `candidate` (local, unpromoted),
 * `secondary` (org-primary), or `primary` (global consensus).
 */
export type MemoryTier = "candidate" | "secondary" | "primary";

/** Read-model for one memory-graph node. */
export interface MemoryNodeSummary {
  id: string;
  organization_id: string;
  intent: string;
  url: string;
  tier: MemoryTier;
  action_type: string;
  /** Confidence in the recorded action, 0..1. */
  confidence: number;
  updated_at: string;
}

/** `GET /memory` response body. */
export interface MemoryResponse {
  nodes: MemoryNodeSummary[];
  total: number;
}

/* ------------------------------------------------------------------------- *
 * Organizations (doc 05 §3.1). The orgs the current actor belongs to. Mirrors
 * `xiosync/api/routers/orgs.py` list read.
 * ------------------------------------------------------------------------- */

/** Organization lifecycle state. */
export type OrgState = "active" | "suspended" | "archived";

/** Subscription plan tier. */
export type OrgPlan = "free" | "pro" | "enterprise";

/** Membership role as stored by the orgs router (`org_memberships.role`). */
export type OrgMemberRole = "owner" | "admin" | "member" | "viewer";

/** Read-model for one organization the caller is a member of. */
export interface OrgSummary {
  id: string;
  name: string;
  display_name: string;
  slug: string;
  plan: OrgPlan;
  state: OrgState;
  /** The caller's membership role in this org. */
  member_role: OrgMemberRole;
  members_count?: number;
}

/** `GET /orgs` response body (mirrors orgs.py `list_orgs`). */
export interface OrgsResponse {
  organizations: OrgSummary[];
  total: number;
}

/* ------------------------------------------------------------------------- *
 * Settings (doc 05 §3.1). The active org's editable configuration surface.
 * ------------------------------------------------------------------------- */

/** `GET /settings` response body — the active organization's settings. */
export interface OrgSettings {
  organization_id: string;
  display_name: string;
  plan: OrgPlan;
  billing_email?: string | null;
  state: OrgState;
  members_count: number;
  /** ISO-8601 timestamp of the last settings mutation, if any. */
  updated_at?: string | null;
}

/* ------------------------------------------------------------------------- *
 * Workers (doc 07 §2). The worker pool that drains the run queue. Admin-scoped
 * read of each worker's liveness.
 * ------------------------------------------------------------------------- */

/** Worker liveness state derived from the heartbeat window. */
export type WorkerState = "online" | "draining" | "offline";

/** Read-model for one worker-pool node. */
export interface WorkerSummary {
  id: string;
  organization_id: string;
  hostname: string;
  state: WorkerState;
  /** Named queue this worker drains. */
  queue: string;
  /** In-flight tasks and the worker's declared capacity. */
  active_tasks: number;
  capacity: number;
  /** ISO-8601 timestamp of the last received heartbeat. */
  last_heartbeat_at: string;
}

/** `GET /workers` response body. */
export interface WorkersResponse {
  workers: WorkerSummary[];
  total: number;
}

/* ------------------------------------------------------------------------- *
 * Admin (platform-scoped, doc 05 §3.3). Runtime-adjustable security config.
 * Mirrors `xiosync/api/routers/admin.py` `GET /admin/config`.
 * ------------------------------------------------------------------------- */

/** Per-scope requests-per-minute thresholds. */
export interface AdminRateLimits {
  general_rpm: number;
  auth_rpm: number;
  agent_rpm: number;
  sync_rpm: number;
}

/** SSRF egress protection configuration. */
export interface AdminSsrfProtection {
  block_private_ips: boolean;
  blocked_hosts: string[];
  /** Empty = allow all public domains. */
  allowed_domains: string[];
}

/** Sandboxed-plugin execution limits. */
export interface AdminPluginExecution {
  allowed_extensions: string[];
  timeout_seconds: number;
}

/** The full runtime security configuration object. */
export interface AdminConfig {
  rate_limits: AdminRateLimits;
  ssrf_protection: AdminSsrfProtection;
  plugin_execution: AdminPluginExecution;
}

/** `GET /admin/config` response body. */
export interface AdminConfigResponse {
  status: string;
  config: AdminConfig;
}
