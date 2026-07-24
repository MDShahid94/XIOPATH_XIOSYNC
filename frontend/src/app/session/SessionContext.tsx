/**
 * Session/auth global state (doc 08 §4: global stores hold only session/auth).
 * Derives the active {@link Authority} from the in-memory access token. The
 * session is memory-only (INV-FE-1): a reload starts anonymous until a silent
 * refresh or fresh login succeeds.
 */
import {
  createContext,
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authApi, tokenStore } from "@/api";
import type { LoginRequest } from "@/api/generated/schema";
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

function sessionFromToken(
  accessToken: string,
  organizationId: string,
): Session {
  const claims = decodeAccessToken(accessToken);
  // Roles are UX-only hints (doc 08 §3). Until the authoritative /auth/session
  // endpoint lands, fall back to the least-privileged sensible defaults.
  const platformRole: PlatformRole =
    claims?.platform_role === "platform_admin" ? "platform_admin" : "none";
  const membershipRole = (claims?.membership_role ??
    "org_member") as MembershipRole;
  return {
    organizationId,
    actorId: claims?.actor_id,
    sessionId: claims?.session_id,
    platformRole,
    membershipRole,
  };
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("anonymous");
  const [session, setSession] = useState<Session | null>(null);

  const login = useCallback(
    async (credentials: LoginRequest): Promise<void> => {
      setStatus("authenticating");
      try {
        const tokens = await authApi.login(credentials);
        tokenStore.set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          accessTokenExpiresAt: Date.parse(tokens.access_token_expires_at),
        });
        setSession(
          sessionFromToken(tokens.access_token, tokens.organization_id),
        );
        setStatus("authenticated");
      } catch (error) {
        tokenStore.clear();
        setSession(null);
        setStatus("anonymous");
        throw error;
      }
    },
    [],
  );

  const logout = useCallback(async (): Promise<void> => {
    try {
      await authApi.logout();
    } finally {
      tokenStore.clear();
      setSession(null);
      setStatus("anonymous");
    }
  }, []);

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
