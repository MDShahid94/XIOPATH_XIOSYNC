/**
 * Plugins route (doc 07 §5, doc 08 §3). Lists the org plugin catalog annotated
 * with each plugin's installation state, and drives the approval-gated install
 * lifecycle (INV-PLUGIN-3). Catalog + installations are fetched in parallel
 * through the single typed client and the view handles every async state
 * (loading / error / empty / success — INV-FE-6) via DataState.
 */
import { useMemo } from "react";
import { DataState } from "@/components/DataState";
import { meetsMembership } from "@/lib/authority";
import { toMessage } from "@/lib/problem";
import { useSession } from "@/app/session/useSession";
import type { InstallationResponse } from "@/api/generated/schema";
import { PluginCard } from "./PluginCard";
import {
  usePluginCatalog,
  usePluginInstallations,
  usePluginLifecycle,
} from "./usePlugins";

export default function PluginsPage() {
  const { session } = useSession();
  const isAdmin = session
    ? meetsMembership(session.membershipRole, "org_admin")
    : false;

  const catalog = usePluginCatalog();
  const installs = usePluginInstallations();
  const { install, approve, activate, canAct } = usePluginLifecycle();

  // Combine the two reads into one status the DataState can render.
  const status =
    catalog.status === "error" || installs.status === "error"
      ? "error"
      : catalog.status === "pending" || installs.status === "pending"
        ? "pending"
        : "success";
  const error = catalog.error ?? installs.error;

  const installationByPlugin = useMemo(() => {
    const map = new Map<string, InstallationResponse>();
    for (const row of installs.data?.installations ?? []) {
      map.set(row.plugin_id, row);
    }
    return map;
  }, [installs.data]);

  const plugins = catalog.data?.plugins ?? [];
  const mutationError = install.error ?? approve.error ?? activate.error;

  function isBusy(pluginId: string, installationId?: string): boolean {
    return (
      (install.isPending && install.variables === pluginId) ||
      (approve.isPending && approve.variables === installationId) ||
      (activate.isPending && activate.variables === installationId)
    );
  }

  function retry(): void {
    if (catalog.isError) void catalog.refetch();
    if (installs.isError) void installs.refetch();
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Plugins
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          Browse registered plugins and manage their approval-gated
          installation. Installing requests approval; an admin then approves and
          activates before a plugin can run.
        </p>
      </header>

      {mutationError ? (
        <div
          className="mb-5 rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {toMessage(mutationError)}
        </div>
      ) : null}

      {!canAct ? (
        <div
          className="mb-5 rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning"
          role="status"
        >
          No actor is resolved for this session, so install actions are
          unavailable.
        </div>
      ) : null}

      <DataState
        status={status}
        error={error}
        onRetry={retry}
        loadingLabel="Loading plugins"
        emptyTitle="No plugins registered"
        emptyMessage="When plugins are registered for your organization, they appear here."
        isEmpty={plugins.length === 0}
      >
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {plugins.map((plugin) => {
            const installation = installationByPlugin.get(plugin.id);
            return (
              <PluginCard
                key={plugin.id}
                plugin={plugin}
                installation={installation}
                isAdmin={isAdmin}
                canAct={canAct}
                busy={isBusy(plugin.id, installation?.id)}
                onInstall={(id) => install.mutate(id)}
                onApprove={(id) => approve.mutate(id)}
                onActivate={(id) => activate.mutate(id)}
              />
            );
          })}
        </ul>
      </DataState>
    </div>
  );
}
