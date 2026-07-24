/**
 * In-memory session token store — the M2 remediation (doc 08 §2, INV-FE-1).
 *
 * Access/refresh tokens live ONLY in this module's closure for the lifetime of
 * the tab. They are NEVER written to `localStorage` or `sessionStorage`, never
 * placed in the URL, and never persisted to disk. A hard page reload
 * intentionally drops the session; recovery is a silent refresh (where cookie
 * transport is available) or a fresh login.
 *
 * The forbidden alternative — `localStorage.getItem('xp_token')` — is exactly
 * the XIOPATH defect this file exists to prevent.
 */

export interface SessionTokens {
  accessToken: string;
  /**
   * Rotating refresh token. Held in memory only. When the API adopts HTTP-only
   * cookie transport (doc 05 §2.3) this becomes `undefined` and the browser
   * carries the refresh cookie automatically.
   */
  refreshToken: string | undefined;
  /** Absolute expiry of the access token (ms epoch) for proactive refresh. */
  accessTokenExpiresAt: number;
}

type Listener = (tokens: SessionTokens | null) => void;

let current: SessionTokens | null = null;
const listeners = new Set<Listener>();

export const tokenStore = {
  get(): SessionTokens | null {
    return current;
  },

  getAccessToken(): string | null {
    return current?.accessToken ?? null;
  },

  getRefreshToken(): string | null {
    return current?.refreshToken ?? null;
  },

  set(tokens: SessionTokens): void {
    current = tokens;
    emit();
  },

  clear(): void {
    current = null;
    emit();
  },

  /** Access token is within `skewMs` of expiry (or already expired). */
  isExpiring(skewMs = 30_000): boolean {
    if (!current) return true;
    return Date.now() >= current.accessTokenExpiresAt - skewMs;
  },

  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

function emit(): void {
  for (const listener of listeners) listener(current);
}

// Dev-time tripwire: fail loudly if any code attempts to persist a token,
// enforcing INV-FE-1 during development.
if (import.meta.env.DEV && typeof window !== "undefined") {
  const guard = (storage: Storage, label: string): void => {
    const original = storage.setItem.bind(storage);
    storage.setItem = (key: string, value: string): void => {
      if (/token|jwt|xp_token|access|refresh/i.test(key)) {
        throw new Error(
          `[INV-FE-1] Refused to write "${key}" to ${label}. ` +
            "Session tokens must stay in memory (doc 08 §2).",
        );
      }
      original(key, value);
    };
  };
  guard(window.localStorage, "localStorage");
  guard(window.sessionStorage, "sessionStorage");
}
