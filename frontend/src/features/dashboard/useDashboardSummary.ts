/**
 * Org-scoped dashboard summary query (doc 08 §3, §4). The key carries the
 * organization id so an org switch invalidates cleanly and no view mixes data
 * from two orgs (INV-FE-5). Fetching flows through the single typed client.
 */
import { useQuery } from "@tanstack/react-query";
import { dashboardApi, orgScopedKey } from "@/api";
import type { DashboardSummary } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

export function useDashboardSummary() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<DashboardSummary>({
    queryKey: orgScopedKey(organizationId ?? "none", "dashboard-summary"),
    queryFn: ({ signal }) => dashboardApi.summary(signal),
    enabled: Boolean(organizationId),
  });
}
