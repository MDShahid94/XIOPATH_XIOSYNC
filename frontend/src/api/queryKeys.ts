/**
 * TanStack Query key factory (doc 08 §4). Keys are resource + `organization_id`
 * so an org switch invalidates cleanly and no rendered view mixes data from two
 * organizations (INV-FE-5).
 *
 * SECURITY (INV-FE-1, M2 remediation): a query key is NEVER allowed to contain
 * an access/refresh token or any secret. Tokens live only in the in-memory
 * `tokenStore`; serialising one into a cache key would surface it in devtools
 * and query state — exactly the persistence this codebase forbids. Keys carry
 * only non-secret identifiers (resource names, org ids, entity ids).
 */

export const sessionKeys = {
  all: ["session"] as const,
  /** The single authoritative session/authority cache entry. */
  current: () => [...sessionKeys.all, "current"] as const,
} as const;

/**
 * Build an org-scoped resource key. The `organization_id` is always part of the
 * key so switching org cannot leak stale cross-org data (INV-FE-5). `rest`
 * carries further non-secret identifiers (entity id, page, filter token).
 */
export function orgScopedKey(
  organizationId: string,
  resource: string,
  ...rest: readonly (string | number)[]
): (string | number)[] {
  return [resource, "org", organizationId, ...rest];
}
