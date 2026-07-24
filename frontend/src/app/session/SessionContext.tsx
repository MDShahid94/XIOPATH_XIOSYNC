/**
 * Session/auth global state (doc 08 §4: global stores hold only session/auth),
 * driven through TanStack Query so the whole app shares one cache-backed source
 * of truth.
 *
 *  - Bootstrap: a single `useQuery` performs a silent refresh on load
 *    (`authApi.bootstrap`) to restore an existing session. The session is
 *    memory-only (INV-FE-1): a hard reload starts anonymous until that refresh
 *    or a fresh login succeeds.
 *  - Login/logout are `useMutation`s that talk to the typed backend API
 *    (INV-FE-1); tokens land in the in-memory `tokenStore` only — never in
 *    `localStorage`/`sessionStorage` or the URL.
 *  - The session cache key (`sessionKeys.current`) carries no token; on logout
 *    all org-scoped caches are dropped so no stale cross-org data survives a
 *    session change (INV-FE-5).
 */
import {
  createContext,
  useCallback,
  useMemo,
  type ReactNode,
} from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { authApi, sessionKeys, tokenStore } from "@/api";
import type { LoginRequest, TokenResponse } from "@/api/generated/schema";
import type {
  Authority,
  MembershipRole,
  PlatformRole,
} from "@/lib/authority";
import { decodeAccessToken } from "@/lib/jwt";

export interface Session extends Authority {
  organizationId: string;
  actorId: string | undefined;
  sessionId: string | undefined;
}

export type AuthStatus = "anonymous" | "authenticating" | "authenticated";

export interface SessionContextValue {
  status: AuthStatus;
  session: Session | null;
  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
}

export const SessionContext = createContext<SessionContextValue | null>(null);

/**
 * Derive the UX-only session view from an access token. Roles are hints for the
 * router guard (doc 08 §3); the server re-checks every request. Returns `null`
 * when no organization can be resolved (treated as anonymous).
 */
function sessionFromToken(
  accessToken: string,
  organizationId?: string,
): Session | null {
  const claims = decodeAccessToken(accessToken);
  const orgId = organizationId ?? claims?.org_id;
  if (!orgId) return null;
  const platformRole: PlatformRole =
    claims?.platform_role === "platform_admin" ? "platform_admin" : "none";
  const membershipRole = (claims?.membership_role ??
    "org_member") as MembershipRole;
  return {
    organizationId: orgId,
    actorId: claims?.actor_id,
    sessionId: claims?.session_id,
    platformRole,
    membershipRole,
  };
}

/** Persist a token payload to the in-memory store (INV-FE-1) and derive state. */
function adoptTokens(tokens: TokenResponse): Session | null {
  tokenStore.set({
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    accessTokenExpiresAt: Date.parse(tokens.access_token_expires_at),
  });
  return sessionFromToken(tokens.access_token, tokens.organization_id);
}

/** Restore an existing session (in-memory token reuse, else silent refresh). */
async function bootstrapSession(): Promise<Session | null> {
  const existing = tokenStore.get();
  if (existing && !tokenStore.isExpiring()) {
    return sessionFromToken(existing.accessToken);
  }
  const tokens = await authApi.bootstrap();
  if (!tokens) {
    tokenStore.clear();
    return null;
  }
  return adoptTokens(tokens);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const sessionQuery = useQuery<Session | null>({
    queryKey: sessionKeys.current(),
    queryFn: bootstrapSession,
    // The session is authoritative for the tab's lifetime; it changes only via
    // the login/logout mutations below, never a background refetch.
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  });

  const loginMutation = useMutation<Session, unknown, LoginRequest>({
    mutationFn: async (credentials) => {
      const tokens = await authApi.login(credentials);
      const session = adoptTokens(tokens);
      if (!session) {
        throw new Error("Login succeeded but no organization was resolved.");
      }
      return session;
    },
    onSuccess: (session) => {
      queryClient.setQueryData(sessionKeys.current(), session);
    },
    onError: () => {
      tokenStore.clear();
      queryClient.setQueryData(sessionKeys.current(), null);
    },
  });

  const logoutMutation = useMutation<void, unknown, void>({
    mutationFn: async () => {
      await authApi.logout();
    },
    // Always tear down locally, even if the network logout failed.
    onSettled: () => {
      tokenStore.clear();
      queryClient.setQueryData(sessionKeys.current(), null);
      // Drop every org-scoped cache so no stale cross-org data survives the
      // session change (INV-FE-5); keep the session entry we just reset.
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== sessionKeys.all[0],
      });
    },
  });

  const { mutateAsync: loginAsync } = loginMutation;
  const { mutateAsync: logoutAsync } = logoutMutation;

  const login = useCallback(
    async (credentials: LoginRequest): Promise<void> => {
      await loginAsync(credentials);
    },
    [loginAsync],
  );

  const logout = useCallback(async (): Promise<void> => {
    await logoutAsync();
  }, [logoutAsync]);

  const session = sessionQuery.data ?? null;

  const status: AuthStatus =
    loginMutation.isPending || sessionQuery.isPending
      ? "authenticating"
      : session
        ? "authenticated"
        : "anonymous";

  const value = useMemo<SessionContextValue>(
    () => ({ status, session, login, logout }),
    [status, session, login, logout],
  );

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}
