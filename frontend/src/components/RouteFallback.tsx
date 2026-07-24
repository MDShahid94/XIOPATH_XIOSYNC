/**
 * Real loading fallback for route-level code splitting (doc 08 §5, §8).
 * A spinner-only-then-crash path is a defect — routes pair this with an error
 * boundary and an empty/success state.
 */
export function RouteFallback({ label = "Loading" }: { label?: string }) {
  return (
    <div className="route-fallback" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}
