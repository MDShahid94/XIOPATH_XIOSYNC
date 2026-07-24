/**
 * Placeholder dashboard route (doc 08 §3: org-scoped summary for any member).
 * Structural foundation only — data-driven widgets arrive in later steps and
 * MUST each handle loading/empty/error/success (INV-FE-6). For now it confirms
 * the guarded route renders and exposes sign-out.
 */
import { useSession } from "@/app/session/useSession";

export default function DashboardPage() {
  const { session, logout } = useSession();

  return (
    <main className="dashboard-page">
      <header className="dashboard-header">
        <h1>Dashboard</h1>
        <button type="button" onClick={() => void logout()}>
          Sign out
        </button>
      </header>

      <section aria-label="Active session">
        <h2>Session</h2>
        <dl>
          <dt>Organization</dt>
          <dd>{session?.organizationId ?? "—"}</dd>
          <dt>Membership role</dt>
          <dd>{session?.membershipRole ?? "—"}</dd>
          <dt>Platform role</dt>
          <dd>{session?.platformRole ?? "—"}</dd>
        </dl>
      </section>

      <p className="placeholder-note">
        Org-scoped summary widgets are added in a later Phase 6 step.
      </p>
    </main>
  );
}
