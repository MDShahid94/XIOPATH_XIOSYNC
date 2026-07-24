/**
 * One dead-letter record and its governed resolution flow (INV-DLQ-1/2/3).
 *
 *   open          → attach a diagnosis ("Propose") → investigating (INV-DLQ-2)
 *   investigating → resolve, gated by an explicit-approval checkbox that maps
 *                   to `explicit_approval: true` → resolved (INV-DLQ-3)
 *   resolved      → read-only
 *
 * The explicit-approval gate is surfaced in the UI so a resolve cannot be
 * triggered by accident; the server enforces the same gate (doc 08 §3).
 */
import { useState } from "react";
import type { DeadLetterResponse } from "@/api/generated/schema";
import { DeadLetterStatusBadge } from "@/components/StatusBadge";

interface DlqCardProps {
  item: DeadLetterResponse;
  busy: boolean;
  onPropose: (deadLetterId: string, note: string) => void;
  onResolve: (deadLetterId: string) => void;
}

const PRIMARY_BUTTON =
  "inline-flex items-center justify-center rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50";
const SECONDARY_BUTTON =
  "inline-flex items-center justify-center rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50";

export function DlqCard({ item, busy, onPropose, onResolve }: DlqCardProps) {
  const [note, setNote] = useState("");
  const [approved, setApproved] = useState(false);

  const diagnosisNote =
    item.diagnosis && typeof item.diagnosis.note === "string"
      ? (item.diagnosis.note as string)
      : null;

  function renderActions() {
    if (item.state === "open") {
      return (
        <div className="mt-4 border-t border-border pt-4">
          <label
            htmlFor={`dlq-note-${item.id}`}
            className="block text-xs font-medium text-foreground"
          >
            Diagnosis note
          </label>
          <textarea
            id={`dlq-note-${item.id}`}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={2}
            placeholder="Describe the suspected cause. Advisory only — this never edits the live spec."
            className="mt-1.5 w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:border-ring"
          />
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              className={PRIMARY_BUTTON}
              disabled={busy || note.trim().length === 0}
              onClick={() => onPropose(item.id, note.trim())}
            >
              {busy ? "Submitting…" : "Propose correction"}
            </button>
          </div>
        </div>
      );
    }

    if (item.state === "investigating") {
      return (
        <div className="mt-4 border-t border-border pt-4">
          <label className="flex items-start gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={approved}
              onChange={(event) => setApproved(event.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-border text-primary focus-visible:border-ring"
            />
            <span className="text-pretty">
              I explicitly approve resolving this record. Auto-resolution is
              never permitted.
            </span>
          </label>
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              className={SECONDARY_BUTTON}
              disabled={busy || !approved}
              onClick={() => onResolve(item.id)}
            >
              {busy ? "Resolving…" : "Resolve"}
            </button>
          </div>
        </div>
      );
    }

    return null;
  }

  return (
    <li className="flex flex-col rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">Task</p>
          <p className="truncate font-mono text-sm text-foreground">
            {item.task_id}
          </p>
        </div>
        <DeadLetterStatusBadge state={item.state} />
      </div>

      <p className="mt-3 text-sm text-foreground/80">
        <span className="text-muted-foreground">Failure: </span>
        {item.failure_reason ?? "No reason recorded."}
      </p>

      {diagnosisNote ? (
        <p className="mt-2 rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Diagnosis: </span>
          {diagnosisNote}
        </p>
      ) : null}

      {item.proposal_id ? (
        <p className="mt-2 font-mono text-xs text-muted-foreground">
          Proposal {item.proposal_id}
        </p>
      ) : null}

      {renderActions()}
    </li>
  );
}
