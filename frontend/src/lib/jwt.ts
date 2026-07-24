/**
 * Decode (NOT verify) a JWT payload for UX display only. The access token
 * carries `session_id`, `org_id`, `actor_id` (doc 05 §2.2); the client reads
 * them to render identity/org context. Signature verification and all security
 * decisions happen server-side (doc 08 §3) — this must never gate authority.
 */
export interface AccessTokenClaims {
  session_id?: string;
  org_id?: string;
  actor_id?: string;
  platform_role?: string;
  membership_role?: string;
  exp?: number;
}

function base64UrlDecode(segment: string): string {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/");
  const normalized = padded.padEnd(
    padded.length + ((4 - (padded.length % 4)) % 4),
    "=",
  );
  return atob(normalized);
}

export function decodeAccessToken(token: string): AccessTokenClaims | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const payload = parts[1];
  if (!payload) return null;
  try {
    return JSON.parse(base64UrlDecode(payload)) as AccessTokenClaims;
  } catch {
    return null;
  }
}
