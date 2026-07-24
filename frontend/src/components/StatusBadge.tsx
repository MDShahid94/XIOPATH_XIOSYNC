/**
 * Small semantic status pill. Installation/plugin lifecycle states map onto the
 * three status accent tokens (success / warning / danger) plus a neutral muted
 * tone, so the palette stays small and the meaning is consistent everywhere.
 */
import type { InstallationState, PluginState } from "@/api/generated/schema";

type Tone = "success" | "warning" | "danger" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  neutral: "bg-muted text-muted-foreground",
};

const INSTALLATION_TONE: Record<InstallationState, Tone> = {
  active: "success",
  approved: "success",
  pending_approval: "warning",
  suspended: "warning",
  revoked: "danger",
};

const INSTALLATION_LABEL: Record<InstallationState, string> = {
  active: "Active",
  approved: "Approved",
  pending_approval: "Pending approval",
  suspended: "Suspended",
  revoked: "Revoked",
};

const PLUGIN_TONE: Record<PluginState, Tone> = {
  registered: "success",
  deprecated: "neutral",
};

function Pill({ tone, children }: { tone: Tone; children: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
    >
      <span
        className="h-1.5 w-1.5 rounded-full bg-current"
        aria-hidden="true"
      />
      {children}
    </span>
  );
}

export function InstallationStatusBadge({
  state,
}: {
  state: InstallationState;
}) {
  return <Pill tone={INSTALLATION_TONE[state]}>{INSTALLATION_LABEL[state]}</Pill>;
}

export function PluginStatusBadge({ state }: { state: PluginState }) {
  return (
    <Pill tone={PLUGIN_TONE[state]}>
      {state === "registered" ? "Registered" : "Deprecated"}
    </Pill>
  );
}
