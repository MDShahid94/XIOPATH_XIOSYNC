/**
 * Capability-registry query (doc 05 §2, doc 08 §4). Org-scoped so an org switch
 * invalidates cleanly (INV-FE-5). Transport flows through the single typed
 * client (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { capabilitiesApi, orgScopedKey } from "@/api";
import type { CapabilitiesResponse } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const CAPABILITIES_RESOURCE = "capabilities";

export function useCapabilities() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<CapabilitiesResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", CAPABILITIES_RESOURCE),
    queryFn: ({ signal }) => capabilitiesApi.list(signal),
    enabled: Boolean(organizationId),
  });
}
