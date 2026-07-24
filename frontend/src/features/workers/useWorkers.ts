/**
 * Worker-pool query (doc 07 §2, doc 08 §4). Org-scoped so an org switch
 * invalidates cleanly (INV-FE-5). Transport flows through the single typed
 * client (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { orgScopedKey, workersApi } from "@/api";
import type { WorkersResponse } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const WORKERS_RESOURCE = "workers";

export function useWorkers() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<WorkersResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", WORKERS_RESOURCE),
    queryFn: ({ signal }) => workersApi.list(signal),
    enabled: Boolean(organizationId),
  });
}
