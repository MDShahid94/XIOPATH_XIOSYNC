/**
 * A titled group of key/value config rows for the admin panel. Presentational
 * only — the runtime security config is rendered read-only here; mutating it
 * (rate limits, SSRF allowlists, plugin limits) is a governed action for a
 * later step.
 */
import type { ReactNode } from "react";

export interface ConfigRow {
  label: string;
  value: ReactNode;
}

export function AdminConfigSection({
  title,
  description,
  rows,
}: {
  title: string;
  description: string;
  rows: readonly ConfigRow[];
}) {
  return (
    <section className="rounded-lg border border-border bg-card shadow-sm">
      <header className="border-b border-border px-5 py-4">
        <h2 className="font-semibold text-foreground">{title}</h2>
        <p className="mt-0.5 text-xs text-muted-foreground text-pretty">
          {description}
        </p>
      </header>
      <dl className="divide-y divide-border">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-start justify-between gap-4 px-5 py-3"
          >
            <dt className="text-sm text-muted-foreground">{row.label}</dt>
            <dd className="text-right text-sm text-foreground">{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
