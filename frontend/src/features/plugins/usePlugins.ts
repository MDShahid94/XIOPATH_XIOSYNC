/**
 * Plugin control-plane queries + mutations (doc 07 §5, doc 08 §4).
 *
 *  - Reads (catalog, installations) are org-scoped queries so an org switch
 *    invalidates cleanly (INV-FE-5).
 *  - Writes go through the approval-gated lifecycle (INV-PLUGIN-3): `install`
 *    requests an install, `approve` mints the grant, `activate` makes it
 *    operational. Each mutation invalidates the installations query so the UI
 *    reflects server truth rather than an optimistic guess.
 *
 * All transport flows through the single typed client (doc 08 §1).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { orgScopedKey, pluginsApi } from "@/api";
import type {
  InstallationsResponse,
  PluginCatalogResponse,
} from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const CATALOG_RESOURCE = "plugin-catalog";
const INSTALLATIONS_RESOURCE = "plugin-installations";

export function usePluginCatalog() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<PluginCatalogResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", CATALOG_RESOURCE),
    queryFn: ({ signal }) => pluginsApi.listCatalog(signal),
    enabled: Boolean(organizationId),
  });
}

export function usePluginInstallations() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<InstallationsResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", INSTALLATIONS_RESOURCE),
    queryFn: ({ signal }) => pluginsApi.listInstallations(signal),
    enabled: Boolean(organizationId),
  });
}

/**
 * The approval-gated lifecycle mutations. `actorId` is the current session
 * actor; it is required to request an install or approve one (the server also
 * re-checks authority — the client never trusts itself, doc 08 §3).
 */
export function usePluginLifecycle() {
  const queryClient = useQueryClient();
  const { session } = useSession();
  const organizationId = session?.organizationId ?? "none";
  const actorId = session?.actorId;

  function invalidateInstallations(): Promise<void> {
    return queryClient.invalidateQueries({
      queryKey: orgScopedKey(organizationId, INSTALLATIONS_RESOURCE),
    });
  }

  const install = useMutation({
    mutationFn: (pluginId: string) => {
      if (!actorId) {
        throw new Error("No actor is resolved for the current session.");
      }
      return pluginsApi.install(pluginId, { requested_by: actorId });
    },
    onSuccess: invalidateInstallations,
  });

  const approve = useMutation({
    mutationFn: (installationId: string) => {
      if (!actorId) {
        throw new Error("No actor is resolved for the current session.");
      }
      return pluginsApi.approve(installationId, { approved_by: actorId });
    },
    onSuccess: invalidateInstallations,
  });

  const activate = useMutation({
    mutationFn: (installationId: string) =>
      pluginsApi.activate(installationId),
    onSuccess: invalidateInstallations,
  });

  return { install, approve, activate, canAct: Boolean(actorId) };
}
