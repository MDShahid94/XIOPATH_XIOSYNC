/**
 * One plugin in the catalog with its installation lifecycle affordance. The
 * action reflects the approval-gated lifecycle (INV-PLUGIN-3):
 *
 *   (none)           → "Request install"      (any member)
 *   pending_approval → "Approve"              (admin only; mints the grant)
 *   approved         → "Activate"             (admin only; makes it operational)
 *   active/…         → status badge only
 *
 * Approve/activate controls are hidden for non-admins (UX only — the server
 * re-checks authority on every request, doc 08 §3).
 */
import type {
  InstallationResponse,
  PluginSummary,
} from "@/api/generated/schema";
import {
  InstallationStatusBadge,
  PluginStatusBadge,
} from "@/components/StatusBadge";

interface PluginCardProps {
  plugin: PluginSummary;
  installation?: InstallationResponse | undefined;
  isAdmin: boolean;
  canAct: boolean;
  busy: boolean;
  onInstall: (pluginId: string) => void;
  onApprove: (installationId: string) => void;
  onActivate: (installationId: string) => void;
}

const ACTION_BUTTON =
  "inline-flex items-center justify-center rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50";

export function PluginCard({
  plugin,
  installation,
  isAdmin,
  canAct,
  busy,
  onInstall,
  onApprove,
  onActivate,
}: PluginCardProps) {
  const state = installation?.state;

  function renderAction() {
    if (!installation) {
      return (
        <button
          type="button"
          className={ACTION_BUTTON}
          disabled={busy || !canAct}
          onClick={() => onInstall(plugin.id)}
        >
          {busy ? "Requesting…" : "Request install"}
        </button>
      );
    }
    if (state === "pending_approval" && isAdmin) {
      return (
        <button
          type="button"
          className={ACTION_BUTTON}
          disabled={busy}
          onClick={() => onApprove(installation.id)}
        >
          {busy ? "Approving…" : "Approve"}
        </button>
      );
    }
    if (state === "approved" && isAdmin) {
      return (
        <button
          type="button"
          className={ACTION_BUTTON}
          disabled={busy}
          onClick={() => onActivate(installation.id)}
        >
          {busy ? "Activating…" : "Activate"}
        </button>
      );
    }
    return null;
  }

  return (
    <li className="flex flex-col rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-foreground">
            {plugin.name}
          </h3>
          <p className="font-mono text-xs text-muted-foreground">
            v{plugin.version}
          </p>
        </div>
        <PluginStatusBadge state={plugin.state} />
      </div>

      <p className="mt-3 line-clamp-3 text-sm text-muted-foreground">
        {plugin.description ?? "No description provided."}
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="text-muted-foreground">Capability</dt>
          <dd className="mt-0.5 truncate font-mono text-foreground">
            {plugin.required_capability}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">RPC methods</dt>
          <dd className="mt-0.5 tabular-nums text-foreground">
            {plugin.rpc_method_count}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Network</dt>
          <dd className="mt-0.5 text-foreground">
            {plugin.network_allowlist_size === 0
              ? "Deny all"
              : `${plugin.network_allowlist_size} allowed`}
          </dd>
        </div>
      </dl>

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-border pt-4">
        <span>
          {installation ? (
            <InstallationStatusBadge state={installation.state} />
          ) : (
            <span className="text-xs text-muted-foreground">Not installed</span>
          )}
        </span>
        {renderAction()}
      </div>
    </li>
  );
}
