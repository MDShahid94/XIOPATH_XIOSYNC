# `api/generated/` — DO NOT HAND-EDIT

This directory holds the **single** API client, generated from the committed
OpenAPI contract (doc 04 §2.3). XIOPATH shipped two drifting clients
(`lib/api.js` + `lib/api-v2.js`, finding M3); XIOSYNC has exactly one, produced
in CI and diffed on every build.

## Regenerating

```bash
# Export the OpenAPI schema from the FastAPI app to ../openapi.json, then:
pnpm gen:api
```

`pnpm gen:api` runs `openapi-typescript` and overwrites `schema.d.ts`. The
generated types are consumed by the transport in `../client.ts` and surfaced as
typed endpoint wrappers in `../endpoints.ts`. Hand-written `fetch` calls to
platform endpoints anywhere outside this client are forbidden (doc 08 §1, §9).

Until the OpenAPI export is wired into CI (Phase 6 Step 2), `schema.d.ts`
contains a hand-authored stub of the auth contract that mirrors
`xiosync/api/routers/auth.py`. It will be replaced wholesale by the generator.
