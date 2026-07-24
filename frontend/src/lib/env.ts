/**
 * Runtime configuration resolved from Vite env vars. Contains no secrets —
 * the frontend holds no signing keys and never persists tokens (doc 08 §1, §2).
 */
export const env = {
  /** Base URL of the single generated API client (doc 08 §1). */
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
  /** WebSocket endpoint; auth is negotiated in the handshake (INV-FE-2). */
  wsUrl: import.meta.env.VITE_WS_URL ?? "/ws",
} as const;
