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
