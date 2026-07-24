/**
 * Rendered when the user is authenticated but lacks a route's authority
 * (doc 08 §3). The guard shows this instead of the content — it never renders
 * a route the user is not authorized for, and never white-screens.
 */
export function AuthorizedEmptyState({
  requirement,
}: {
  requirement: string;
}) {
  return (
    <div className="authorized-empty" role="status">
      <h2>You don&apos;t have access to this area</h2>
      <p>
        This page requires <strong>{requirement}</strong>. Ask an organization
        administrator if you need access.
      </p>
    </div>
  );
}
