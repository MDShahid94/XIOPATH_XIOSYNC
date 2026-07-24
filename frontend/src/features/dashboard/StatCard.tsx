/**
 * A single dashboard metric tile. Number-forward with a quiet label and an
 * optional hint line; an optional accent tone tints the value for the few
 * metrics that carry status meaning (e.g. active runs).
 */
type Accent = "default" | "primary" | "success" | "warning";

const VALUE_CLASS: Record<Accent, string> = {
  default: "text-foreground",
  primary: "text-primary",
  success: "text-success",
  warning: "text-warning",
};

export function StatCard({
  label,
  value,
  hint,
  accent = "default",
}: {
  label: string;
  value: number | string;
  hint?: string;
  accent?: Accent;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      <p
        className={`mt-2 text-3xl font-semibold tabular-nums tracking-tight ${VALUE_CLASS[accent]}`}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
