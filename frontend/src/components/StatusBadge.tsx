/**
 * Small semantic status pill. Installation/plugin lifecycle states map onto the
 * three status accent tokens (success / warning / danger) plus a neutral muted
 * tone, so the palette stays small and the meaning is consistent everywhere.
 */
import type {
  DeadLetterState,
  InstallationState,
  PluginState,
  WorkflowRunState,
  WorkflowState,
} from "@/api/generated/schema";

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

const WORKFLOW_TONE: Record<WorkflowState, Tone> = {
  draft: "neutral",
  published: "success",
  deprecated: "neutral",
};

const WORKFLOW_LABEL: Record<WorkflowState, string> = {
  draft: "Draft",
  published: "Published",
  deprecated: "Deprecated",
};

export function WorkflowStatusBadge({ state }: { state: WorkflowState }) {
  return <Pill tone={WORKFLOW_TONE[state]}>{WORKFLOW_LABEL[state]}</Pill>;
}

const RUN_TONE: Record<WorkflowRunState, Tone> = {
  queued: "neutral",
  running: "warning",
  paused: "warning",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
};

const RUN_LABEL: Record<WorkflowRunState, string> = {
  queued: "Queued",
  running: "Running",
  paused: "Paused",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function RunStatusBadge({ state }: { state: WorkflowRunState }) {
  return <Pill tone={RUN_TONE[state]}>{RUN_LABEL[state]}</Pill>;
}

const DEAD_LETTER_TONE: Record<DeadLetterState, Tone> = {
  open: "danger",
  investigating: "warning",
  resolved: "success",
};

const DEAD_LETTER_LABEL: Record<DeadLetterState, string> = {
  open: "Open",
  investigating: "Investigating",
  resolved: "Resolved",
};

export function DeadLetterStatusBadge({ state }: { state: DeadLetterState }) {
  return <Pill tone={DEAD_LETTER_TONE[state]}>{DEAD_LETTER_LABEL[state]}</Pill>;
}
