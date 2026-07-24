/**
 * Platform admin config query (doc 05 §3.3, doc 08 §4). This is a
 * PLATFORM-scoped resource, not org-scoped — the runtime security config is
 * cross-org — so the key is a static platform key rather than `orgScopedKey`
 * (INV-FE-5 concerns org data leakage; there is no org dimension here). The
 * route guard restricts this to platform admins and the server re-checks.
 * Transport flows through the single typed client (doc 08 §1).
 */
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/api";
import type { AdminConfigResponse } from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

/** Static platform-scoped key; carries no org id and no secret (INV-FE-1). */
const ADMIN_CONFIG_KEY = ["admin", "config"] as const;

export function useAdminConfig() {
  const { session } = useSession();
  const isPlatformAdmin = session?.platformRole === "platform_admin";

  return useQuery<AdminConfigResponse>({
    queryKey: ADMIN_CONFIG_KEY,
    queryFn: ({ signal }) => adminApi.config(signal),
    enabled: isPlatformAdmin,
  });
}
