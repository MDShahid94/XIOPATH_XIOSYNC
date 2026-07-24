/**
 * THE single API client (doc 08 §1). All platform HTTP goes through here.
 * Hand-written `fetch` to platform endpoints elsewhere is forbidden (§9, M3).
 *
 * Transport contract (doc 08 §2, doc 05 §2.3):
 *  - Access token attached as `Authorization: Bearer` from the in-memory store.
 *  - `credentials: "include"` so HTTP-only session/CSRF cookies flow when the
 *    API adopts cookie transport — no token ever touches storage or the URL.
 *  - A 401 triggers exactly one silent refresh, then a single retry; concurrent
 *    callers share one in-flight refresh so we never stampede the endpoint.
 */
import { env } from "@/lib/env";
import { isProblem, ProblemError } from "@/lib/problem";
import type {
  RefreshRequest,
  TokenResponse,
} from "@/api/generated/schema";
import { tokenStore } from "./tokenStore";

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** Skip the auth header + refresh dance (login/refresh are public). */
  anonymous?: boolean;
  headers?: Record<string, string>;
}

const AUTH_REFRESH_PATH = "/auth/refresh";

let refreshInFlight: Promise<boolean> | null = null;

function url(path: string): string {
  const base = env.apiBaseUrl.replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function raw(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...options.headers,
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (!options.anonymous) {
    const token = tokenStore.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  return fetch(url(path), {
    method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
    headers,
    credentials: "include",
    ...(options.body !== undefined
      ? { body: JSON.stringify(options.body) }
      : {}),
    ...(options.signal ? { signal: options.signal } : {}),
  });
}

/** Attempt one silent refresh; returns whether a fresh access token is set. */
async function refreshTokens(): Promise<boolean> {
  const refreshToken = tokenStore.getRefreshToken();
  // With cookie transport the refresh cookie is sent automatically, so an
  // absent in-memory refresh token is not necessarily fatal — still attempt.
  const payload: RefreshRequest | undefined = refreshToken
    ? { refresh_token: refreshToken }
    : undefined;
  try {
    const response = await raw(AUTH_REFRESH_PATH, {
      method: "POST",
      anonymous: true,
      ...(payload ? { body: payload } : {}),
    });
    if (!response.ok) {
      tokenStore.clear();
      return false;
    }
    const tokens = (await parseBody(response)) as TokenResponse;
    tokenStore.set({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      accessTokenExpiresAt: Date.parse(tokens.access_token_expires_at),
    });
    return true;
  } catch {
    tokenStore.clear();
    return false;
  }
}

/** Coalesce concurrent refreshes into a single in-flight request. */
function ensureRefreshed(): Promise<boolean> {
  refreshInFlight ??= refreshTokens().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function toResult<T>(response: Response): Promise<T> {
  const body = await parseBody(response);
  if (response.ok) return body as T;
  if (isProblem(body)) throw new ProblemError(body);
  throw new ProblemError(
    response.status,
    "request_failed",
    response.statusText || "Request failed",
  );
}

/** Perform a typed request through the single client. */
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await raw(path, options);

  if (
    response.status === 401 &&
    !options.anonymous &&
    path !== AUTH_REFRESH_PATH
  ) {
    const refreshed = await ensureRefreshed();
    if (refreshed) {
      const retry = await raw(path, options);
      return toResult<T>(retry);
    }
  }

  return toResult<T>(response);
}

export const apiClient = { request } as const;
