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
