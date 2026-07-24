/**
 * Admin route (doc 05 §3.3, doc 08 §3). Platform-administrator view of the
 * runtime security configuration (rate limits, SSRF protection, plugin
 * execution limits). Platform-scoped — the route guard restricts to platform
 * admins and the server re-checks. Data flows through the single typed client
 * via `useAdminConfig`, and the view handles every async state —
 * loading / error / empty / success (INV-FE-6) — via DataState. Read-only.
 */
import { DataState } from "@/components/DataState";
import { StatusPill } from "@/components/StatusBadge";
import { AdminConfigSection, type ConfigRow } from "./AdminConfigSection";
import { useAdminConfig } from "./useAdminConfig";

function boolPill(value: boolean): ConfigRow["value"] {
  return (
    <StatusPill tone={value ? "success" : "neutral"}>
      {value ? "Enabled" : "Disabled"}
    </StatusPill>
  );
}

function listValue(values: readonly string[], emptyLabel: string) {
  if (values.length === 0) {
    return <span className="text-muted-foreground">{emptyLabel}</span>;
  }
  return (
    <span className="font-mono text-xs text-foreground">
      {values.join(", ")}
    </span>
  );
}

export default function AdminPage() {
  const { data, status, error, isFetching, refetch } = useAdminConfig();
  const config = data?.config;

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          Admin
        </h1>
        <p className="mt-1 text-sm text-muted-foreground text-pretty">
          Platform-wide runtime security configuration. These parameters apply
          across every organization; changes are audited.
        </p>
      </header>

      <DataState
        status={status}
        error={error}
        onRetry={() => void refetch()}
        loadingLabel="Loading configuration"
        emptyTitle="No configuration available"
        emptyMessage="The runtime security configuration could not be loaded."
        isEmpty={!config}
      >
        {config ? (
          <div className="flex flex-col gap-5">
            <AdminConfigSection
              title="Rate limits"
              description="Per-scope request ceilings, in requests per minute."
              rows={[
                {
                  label: "General",
                  value: `${config.rate_limits.general_rpm} rpm`,
                },
                { label: "Auth", value: `${config.rate_limits.auth_rpm} rpm` },
                {
                  label: "Agent",
                  value: `${config.rate_limits.agent_rpm} rpm`,
                },
                { label: "Sync", value: `${config.rate_limits.sync_rpm} rpm` },
              ]}
            />

            <AdminConfigSection
              title="SSRF protection"
              description="Egress controls applied to outbound requests."
              rows={[
                {
                  label: "Block private IPs",
                  value: boolPill(config.ssrf_protection.block_private_ips),
                },
                {
                  label: "Blocked hosts",
                  value: listValue(
                    config.ssrf_protection.blocked_hosts,
                    "None",
                  ),
                },
                {
                  label: "Allowed domains",
                  value: listValue(
                    config.ssrf_protection.allowed_domains,
                    "All public domains",
                  ),
                },
              ]}
            />

            <AdminConfigSection
              title="Plugin execution"
              description="Sandbox limits applied to plugin runs."
              rows={[
                {
                  label: "Allowed extensions",
                  value: listValue(
                    config.plugin_execution.allowed_extensions,
                    "None",
                  ),
                },
                {
                  label: "Timeout",
                  value: `${config.plugin_execution.timeout_seconds}s`,
                },
              ]}
            />
          </div>
        ) : null}

        {isFetching && config ? (
          <p className="mt-3 text-xs text-muted-foreground" role="status">
            Refreshing…
          </p>
        ) : null}
      </DataState>
    </div>
  );
}
