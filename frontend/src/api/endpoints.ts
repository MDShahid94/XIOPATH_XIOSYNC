/**
 * Typed endpoint surface. These wrappers are the ONLY callers of the single
 * client (doc 08 §1). When the OpenAPI generator lands (Phase 6 Step 2) this
 * module becomes generated typed hooks; the transport in `client.ts` stays.
 */
import type {
  LoginRequest,
  LogoutResponse,
  RefreshRequest,
  TokenResponse,
} from "@/api/generated/schema";
import { request } from "./client";

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
} as const;
