/**
 * Login route (doc 08 §3). Foundational, accessible form: labelled inputs,
 * programmatic error messaging (INV-FE-8), and explicit submit/error states
 * (INV-FE-6). Credentials post over HTTP through the single client; the token
 * lands in memory only (INV-FE-1).
 */
import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useSession } from "@/app/session/useSession";
import { ROUTES } from "@/app/routes";
import { toMessage } from "@/lib/problem";

interface LocationState {
  from?: string;
}

export default function LoginPage() {
  const { login, status } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [organizationId, setOrganizationId] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submitting = status === "authenticating";

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    try {
      await login({
        organization_id: organizationId.trim(),
        email: email.trim(),
        password,
      });
      const from = (location.state as LocationState | null)?.from;
      navigate(from ?? ROUTES.dashboard.path, { replace: true });
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <h1>Sign in to XIOSYNC</h1>

        <label htmlFor="organization_id">Organization ID</label>
        <input
          id="organization_id"
          name="organization_id"
          autoComplete="off"
          required
          value={organizationId}
          onChange={(event) => setOrganizationId(event.target.value)}
        />

        <label htmlFor="email">Email</label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        <button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
