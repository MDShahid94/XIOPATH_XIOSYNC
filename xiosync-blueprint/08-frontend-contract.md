# 08 — Frontend Contract

> Normative. Defines frontend reliability, accessibility, state, transport, and
> the route/permission matrix. Remediates M2 (localStorage/URL tokens), M3
> (duplicate clients), and enforces doc 01 §4.5. RFC 2119 keywords binding.

---

## 1. Stack & structure

- **React + TypeScript** (strict). No plain-JS modules in application code
  (XIOPATH's frontend was untyped `.jsx`, which let API-shape drift go
  unnoticed).
- **One generated API client** produced from the committed OpenAPI contract
  (doc 04 §2.3). XIOPATH shipped `lib/api.js` **and** `lib/api-v2.js` (M3);
  XIOSYNC has exactly one, regenerated in CI and diffed. Hand-written fetch calls
  to platform endpoints are forbidden outside the generated client.
- Structure by **domain feature**, not by build phase (L1):
  ```
  frontend/src/
    api/            generated client + typed hooks (never hand-edited)
    app/            router, providers, guards
    features/<domain>/   (auth, actors, capabilities, grants, workflows,
                          runs, workers, events, memory, orgs, admin)
    components/     shared presentational components
    lib/            client utilities (no secrets, no token storage)
  ```

---

## 2. Transport & auth (M2 remediation)

- **INV-FE-1:** Access tokens are **never** written to `localStorage` or
  `sessionStorage` (kills M2's `localStorage.getItem('xp_token')`). Session
  transport is **HTTP-only, `Secure`, `SameSite=Strict` cookies**, or a strictly
  **memory-held** access token refreshed silently via the refresh endpoint
  (doc 05 §2.3).
- **INV-FE-2:** The WebSocket authenticates in the **handshake** (cookie or
  `Sec-WebSocket-Protocol` subprotocol). A token in the WS **query string is
  forbidden** (kills M2's `?token=${token}`; doc 05 §2.3).
- **INV-FE-3:** All mutations go over HTTP (where authz + audit are uniform,
  doc 04 §2.3). The WS is **receive-only** typed, org-scoped event frames.
- CSRF: with cookie transport, state-changing requests carry a CSRF token
  (double-submit or header) validated server-side; `SameSite=Strict` is the
  first line, the token is defense-in-depth.

---

## 3. Route / permission matrix

**INV-FE-4:** Every route **declares its required authority** (platform role,
org membership role, and/or a capability grant). The router guard resolves the
current `OrgContext` (from the session) and **never renders** a route the user
is not authorized for — it redirects or shows an authorized-empty state. Client
guards are UX only; the server re-checks every request (doc 05 §4). The client
never trusts itself for security.

| Route | Requires | Notes |
|---|---|---|
| `/login`, `/signup` | anonymous | signup → `org_member` only (doc 05 §1.1) |
| `/` dashboard | any member | org-scoped summary |
| `/actors`, `/capabilities`, `/grants` | `org_member`+ | grant mgmt needs `org_admin` |
| `/workflows`, `/runs` | `org_member`+ | publish/run gated by grant |
| `/events`, `/memory` | `org_member`+ | read-only audit/memory views |
| `/workers` | `org_admin`+ | enrollment/approval |
| `/orgs`, `/settings` | `org_admin`/`org_owner` | membership, org state |
| `/admin/*` | `platform_admin` | cross-org, audited (doc 05 §3.3) |

There are **no** `agents` and `actors` twin pages (H1) and no `_v2` route
duplicates (M3): one canonical page per concept.

---

## 4. State management

- **Server state** via a query/cache library (TanStack Query or equivalent),
  keyed by resource + `organization_id`. The active org is part of every cache
  key so switching org cannot leak stale cross-org data in the UI.
- **Local UI state** stays local (component/context); global stores hold only
  session/auth and cross-cutting UI (toasts, command palette).
- **INV-FE-5:** On org switch, all org-scoped caches are invalidated. No
  rendered view ever mixes data from two organizations.

---

## 5. Reliability — every async surface handles four states (doc 01 §4.5)

**INV-FE-6:** Every data-driven view explicitly handles **loading**, **empty**,
**error**, and **success**. A spinner-only-then-crash path is a defect.
- Errors render the typed `application/problem+json` `code`/message (doc 04
  §2.3), not a raw stack or a blank screen.
- A top-level **error boundary** catches render failures per feature area and
  offers recovery, never a white screen (XIOPATH had one `ErrorBoundary`; keep
  it, scope it per route).
- Mutations are optimistic only where safe and always reconcile against the
  server response; failures roll back and surface the error.

---

## 6. Real-time (WebSocket)

- One `/ws` connection per session, authenticated at handshake (§2).
- Frames are **typed** and **org-scoped** by the server; the client validates
  frame shape before dispatch.
- Reconnect with backoff + jitter; on reconnect, refetch authoritative state via
  HTTP (the WS is a change-notification stream, not the source of truth).
- **INV-FE-7:** The client never derives security decisions from WS frames; it
  refetches or re-authorizes via HTTP.

---

## 7. Accessibility (the bar)

**INV-FE-8:** The app meets **WCAG 2.1 AA**:
- Semantic HTML and correct ARIA roles/attributes; every interactive control is
  keyboard-operable with a visible focus ring.
- Color contrast ≥ 4.5:1 for text; state is never conveyed by color alone.
- All images/icons have text alternatives (decorative ones `aria-hidden`).
- Forms have associated labels and programmatic error messaging.
- Modals/command palette trap focus and restore it on close; Escape closes.
- Automated a11y checks (axe) run in CI; violations block merge (doc 09).

---

## 8. Performance

- Route-level code splitting (retain XIOPATH's `React.lazy` approach) with real
  loading fallbacks (§5).
- Web Vitals budgets enforced in CI on key routes: **LCP ≤ 2.5s**, **INP ≤
  200ms**, **CLS ≤ 0.1** (measured, doc 09).
- No blocking data waterfalls: parallelize independent fetches; prefetch on
  intent (hover/focus) for primary navigation.

---

## 9. Frontend anti-patterns (forbidden)

- Access token in `localStorage`/`sessionStorage`. **(M2)**
- Token in the WebSocket query string. **(M2)**
- More than one API client, or hand-written fetches to platform endpoints. **(M3)**
- Twin pages/routes for one concept (`agents`+`actors`, `_v2`). **(H1/M3)**
- A route that renders without declaring/enforcing its required authority. **(§3)**
- A view missing any of loading/empty/error/success. **(§5)**
- Deriving a security decision on the client. **(§3/§6)**
- Untyped API access (plain-JS platform calls). **(§1)**

Any of these is a frontend regression to be reverted.
