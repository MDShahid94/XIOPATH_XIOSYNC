/**
 * Event/audit-stream query (doc 06 §1, doc 08 §4). Org-scoped so an org switch
 * invalidates cleanly (INV-FE-5). Transport flows through the single typed
 * client (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { eventsApi, orgScopedKey } from "@/api";
import type { EventsResponse } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const EVENTS_RESOURCE = "events";

export function useEvents() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<EventsResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", EVENTS_RESOURCE),
    queryFn: ({ signal }) => eventsApi.list(signal),
    enabled: Boolean(organizationId),
  });
}
