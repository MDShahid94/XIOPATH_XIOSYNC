/**
 * Typed endpoint surface. These wrappers are the ONLY callers of the single
 * client (doc 08 §1). When the OpenAPI generator lands (Phase 6 Step 2) this
 * module becomes generated typed hooks; the transport in `client.ts` stays.
 */
import type {
  AdminConfigResponse,
  ApproveRequest,
  CapabilitiesResponse,
  DashboardSummary,
  DeadLetterResponse,
  DeadLettersResponse,
  EventsResponse,
  GrantsResponse,
  InstallationResponse,
  InstallationsResponse,
  InstallRequest,
  LoginRequest,
  LogoutResponse,
  MemoryResponse,
  OrgSettings,
  OrgsResponse,
  PluginCatalogResponse,
  ProposeRequest,
  ProposeResponse,
  RefreshRequest,
  ResolveRequest,
  ResolveResponse,
  RunsResponse,
  TokenResponse,
  WorkersResponse,
  WorkflowsResponse,
} from "@/api/generated/schema";
import { request } from "./client";
import { tokenStore } from "./tokenStore";

export const authApi = {
  login(body: LoginRequest): Promise<TokenResponse> {
    return request<TokenResponse>("/auth/login", { body, anonymous: true });
  },
  refresh(body: RefreshRequest): Promise<TokenResponse> {
    return request<TokenResponse>("/auth/refresh", { body, anonymous: true });
  },
  logout(): Promise<LogoutResponse> {
    return request<LogoutResponse>("/auth/logout", { method: "POST" });
  },
  /**
   * Silent session bootstrap (doc 05 §2.3). There is no `/auth/session` read
   * endpoint, so the authoritative "am I signed in?" answer is a refresh:
   *  - with cookie transport the refresh cookie flows automatically
   *    (`credentials: "include"`), so no body is needed;
   *  - with memory transport an in-memory refresh token is submitted.
   * Resolves to `null` (anonymous) on any failure rather than throwing — a
   * cold reload with no valid session is an expected, non-error state.
   */
  async bootstrap(): Promise<TokenResponse | null> {
    const refreshToken = tokenStore.getRefreshToken();
    try {
      return await request<TokenResponse>("/auth/refresh", {
        method: "POST",
        anonymous: true,
        ...(refreshToken ? { body: { refresh_token: refreshToken } } : {}),
      });
    } catch {
      return null;
    }
  },
} as const;

/**
 * Org-scoped dashboard summary (doc 08 §3). The server derives the org from the
 * session; the client never passes an org id in the URL (INV-FE-5).
 */
export const dashboardApi = {
  summary(signal?: AbortSignal): Promise<DashboardSummary> {
    return request<DashboardSummary>("/dashboard/summary", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Sandboxed-plugin control plane (doc 07 §5). Listing is a read; installing is
 * the first, approval-gated step of the lifecycle (INV-PLUGIN-3) — approve and
 * activate are separate, admin-only transitions.
 */
export const pluginsApi = {
  listCatalog(signal?: AbortSignal): Promise<PluginCatalogResponse> {
    return request<PluginCatalogResponse>("/plugins", {
      ...(signal ? { signal } : {}),
    });
  },
  listInstallations(signal?: AbortSignal): Promise<InstallationsResponse> {
    return request<InstallationsResponse>("/plugins/installations", {
      ...(signal ? { signal } : {}),
    });
  },
  install(
    pluginId: string,
    body: InstallRequest,
  ): Promise<InstallationResponse> {
    return request<InstallationResponse>(
      `/plugins/${encodeURIComponent(pluginId)}/install`,
      { body },
    );
  },
  approve(
    installationId: string,
    body: ApproveRequest,
  ): Promise<InstallationResponse> {
    return request<InstallationResponse>(
      `/plugins/installations/${encodeURIComponent(installationId)}/approve`,
      { body },
    );
  },
  activate(installationId: string): Promise<InstallationResponse> {
    return request<InstallationResponse>(
      `/plugins/installations/${encodeURIComponent(installationId)}/activate`,
      { method: "POST" },
    );
  },
} as const;

/**
 * Workflow definitions (doc 04 §2.1). Org-scoped read; the server derives the
 * org from the session and never trusts an org id in the URL (INV-FE-5).
 */
export const workflowsApi = {
  list(signal?: AbortSignal): Promise<WorkflowsResponse> {
    return request<WorkflowsResponse>("/workflows", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Workflow runs (doc 03 §4.4). Org-scoped read of every run's current
 * lifecycle state.
 */
export const runsApi = {
  list(signal?: AbortSignal): Promise<RunsResponse> {
    return request<RunsResponse>("/runs", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Dead-letter governance (doc 07 §4, INV-DLQ-1/2/3). Listing/inspecting are
 * reads; `propose` advances open → investigating with an advisory diagnosis
 * (INV-DLQ-2), and `resolve` closes investigating → resolved under mandatory
 * explicit approval (INV-DLQ-3). Nothing here auto-resolves a record.
 */
export const dlqApi = {
  list(signal?: AbortSignal): Promise<DeadLettersResponse> {
    return request<DeadLettersResponse>("/dlq", {
      ...(signal ? { signal } : {}),
    });
  },
  get(deadLetterId: string, signal?: AbortSignal): Promise<DeadLetterResponse> {
    return request<DeadLetterResponse>(
      `/dlq/${encodeURIComponent(deadLetterId)}`,
      { ...(signal ? { signal } : {}) },
    );
  },
  propose(
    deadLetterId: string,
    body: ProposeRequest,
  ): Promise<ProposeResponse> {
    return request<ProposeResponse>(
      `/dlq/${encodeURIComponent(deadLetterId)}/propose`,
      { body },
    );
  },
  resolve(
    deadLetterId: string,
    body: ResolveRequest,
  ): Promise<ResolveResponse> {
    return request<ResolveResponse>(
      `/dlq/${encodeURIComponent(deadLetterId)}/resolve`,
      { body },
    );
  },
} as const;

/**
 * Capability registry (doc 05 §2). Org-scoped read of the typed permission
 * vocabulary; the server derives the org from the session (INV-FE-5).
 */
export const capabilitiesApi = {
  list(signal?: AbortSignal): Promise<CapabilitiesResponse> {
    return request<CapabilitiesResponse>("/capabilities", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Grants (doc 05 §3). Org-scoped read of capability→actor bindings; only
 * `active` grants authorize (INV-GRANT-1). Admin-visible.
 */
export const grantsApi = {
  list(signal?: AbortSignal): Promise<GrantsResponse> {
    return request<GrantsResponse>("/grants", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Event/audit stream (doc 06 §1). Org-scoped, append-only read of recent
 * activity.
 */
export const eventsApi = {
  list(signal?: AbortSignal): Promise<EventsResponse> {
    return request<EventsResponse>("/events", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Memory graph (doc 09 §2). Org-scoped read of promoted intents/actions in the
 * tiered execution memory.
 */
export const memoryApi = {
  list(signal?: AbortSignal): Promise<MemoryResponse> {
    return request<MemoryResponse>("/memory", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Organizations (doc 05 §3.1). Lists the orgs the current actor belongs to;
 * the server scopes to the session actor (INV-FE-5).
 */
export const orgsApi = {
  list(signal?: AbortSignal): Promise<OrgsResponse> {
    return request<OrgsResponse>("/orgs", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Active-org settings (doc 05 §3.1). Read of the current organization's
 * editable configuration surface.
 */
export const settingsApi = {
  get(signal?: AbortSignal): Promise<OrgSettings> {
    return request<OrgSettings>("/settings", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Worker pool (doc 07 §2). Org-scoped read of each worker's liveness. Admin
 * visibility only (route guard enforces, server re-checks).
 */
export const workersApi = {
  list(signal?: AbortSignal): Promise<WorkersResponse> {
    return request<WorkersResponse>("/workers", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;

/**
 * Platform admin (doc 05 §3.3). Runtime security configuration read. Mirrors
 * `GET /admin/config`; platform-admin only (route guard + server re-check).
 */
export const adminApi = {
  config(signal?: AbortSignal): Promise<AdminConfigResponse> {
    return request<AdminConfigResponse>("/admin/config", {
      ...(signal ? { signal } : {}),
    });
  },
} as const;
