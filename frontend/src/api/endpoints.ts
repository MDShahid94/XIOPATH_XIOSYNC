/**
 * Typed endpoint surface. These wrappers are the ONLY callers of the single
 * client (doc 08 §1). When the OpenAPI generator lands (Phase 6 Step 2) this
 * module becomes generated typed hooks; the transport in `client.ts` stays.
 */
import type {
  ApproveRequest,
  DashboardSummary,
  InstallationResponse,
  InstallationsResponse,
  InstallRequest,
  LoginRequest,
  LogoutResponse,
  PluginCatalogResponse,
  RefreshRequest,
  TokenResponse,
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
