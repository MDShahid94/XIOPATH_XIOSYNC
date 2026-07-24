/**
 * Active-org settings query (doc 05 §3.1, doc 08 §4). Org-scoped so an org
 * switch invalidates cleanly (INV-FE-5). Transport flows through the single
 * typed client (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { orgScopedKey, settingsApi } from "@/api";
import type { OrgSettings } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const SETTINGS_RESOURCE = "settings";

export function useSettings() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<OrgSettings>({
    queryKey: orgScopedKey(organizationId ?? "none", SETTINGS_RESOURCE),
    queryFn: ({ signal }) => settingsApi.get(signal),
    enabled: Boolean(organizationId),
  });
}
