/**
 * A single, consistent renderer for the four states every data view must handle
 * (INV-FE-6, doc 08 §5): loading, error, empty, and success. Views pass their
 * query status in and only ever render their content in the success+non-empty
 * branch — a spinner-then-crash path is a defect.
 */
import type { ReactNode } from "react";
import { toMessage } from "@/lib/problem";

type Status = "pending" | "error" | "success";

interface DataStateProps {
  status: Status;
  /** Thrown value from the query, rendered as a problem message on error. */
  error?: unknown;
  /** True when the request succeeded but returned no rows. */
  isEmpty?: boolean;
  loadingLabel?: string;
  emptyTitle?: string;
  emptyMessage?: string;
  /** Optional retry handler shown on the error state. */
  onRetry?: () => void;
  children: ReactNode;
}

export function DataState({
  status,
  error,
  isEmpty = false,
  loadingLabel = "Loading",
  emptyTitle = "Nothing here yet",
  emptyMessage = "There is no data to show for this organization.",
  onRetry,
  children,
}: DataStateProps) {
  if (status === "pending") {
    return (
      <div
        className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-6 text-sm text-muted-foreground"
        role="status"
        aria-live="polite"
      >
        <span className="spinner" aria-hidden="true" />
        <span>{loadingLabel}…</span>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div
        className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-5"
        role="alert"
      >
        <p className="text-sm font-semibold text-danger">
          Something went wrong
        </p>
        <p className="mt-1 text-sm text-foreground/80">{toMessage(error)}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex items-center rounded-md border border-danger/40 bg-card px-3 py-1.5 text-sm font-medium text-danger transition-colors hover:bg-danger/10"
          >
            Try again
          </button>
        ) : null}
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-card px-4 py-10 text-center">
        <p className="text-sm font-semibold text-foreground">{emptyTitle}</p>
        <p className="mt-1 text-sm text-muted-foreground">{emptyMessage}</p>
      </div>
    );
  }

  return <>{children}</>;
}
