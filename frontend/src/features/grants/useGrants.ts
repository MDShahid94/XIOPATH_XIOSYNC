/**
 * Grants query (doc 05 §3, doc 08 §4). Org-scoped so an org switch invalidates
 * cleanly (INV-FE-5). Transport flows through the single typed client
 * (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { grantsApi, orgScopedKey } from "@/api";
import type { GrantsResponse } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const GRANTS_RESOURCE = "grants";

export function useGrants() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<GrantsResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", GRANTS_RESOURCE),
    queryFn: ({ signal }) => grantsApi.list(signal),
    enabled: Boolean(organizationId),
  });
}
