/**
 * Organizations query (doc 05 §3.1, doc 08 §4). Lists the orgs the current
 * actor belongs to. Org-scoped key so a session/org change invalidates cleanly
 * (INV-FE-5). Transport flows through the single typed client (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { orgScopedKey, orgsApi } from "@/api";
import type { OrgsResponse } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const ORGS_RESOURCE = "orgs";

export function useOrgs() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<OrgsResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", ORGS_RESOURCE),
    queryFn: ({ signal }) => orgsApi.list(signal),
    enabled: Boolean(organizationId),
  });
}
