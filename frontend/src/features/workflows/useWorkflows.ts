/**
 * Workflow-definition query (doc 04 §2.1, doc 08 §4). Org-scoped so an org
 * switch invalidates cleanly (INV-FE-5). Transport flows through the single
 * typed client (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { orgScopedKey, workflowsApi } from "@/api";
import type { WorkflowsResponse } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const WORKFLOWS_RESOURCE = "workflows";

export function useWorkflows() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<WorkflowsResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", WORKFLOWS_RESOURCE),
    queryFn: ({ signal }) => workflowsApi.list(signal),
    enabled: Boolean(organizationId),
  });
}
