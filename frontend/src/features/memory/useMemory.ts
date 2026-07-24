/**
 * Memory-graph query (doc 09 §2, doc 08 §4). Org-scoped so an org switch
 * invalidates cleanly (INV-FE-5). Transport flows through the single typed
 * client (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { memoryApi, orgScopedKey } from "@/api";
import type { MemoryResponse } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const MEMORY_RESOURCE = "memory";

export function useMemory() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<MemoryResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", MEMORY_RESOURCE),
    queryFn: ({ signal }) => memoryApi.list(signal),
    enabled: Boolean(organizationId),
  });
}
