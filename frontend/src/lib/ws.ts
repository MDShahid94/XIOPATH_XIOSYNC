/**
 * Session WebSocket transport (doc 08 §6).
 *
 *  - INV-FE-2: authenticate in the HANDSHAKE — cookie or `Sec-WebSocket-Protocol`
 *    subprotocol. A `?token=` query string is FORBIDDEN (it leaks into logs).
 *  - INV-FE-3: the socket is RECEIVE-ONLY typed, org-scoped frames. Mutations
 *    go over HTTP. We never `send()` state changes here.
 *  - INV-FE-7: the client never derives a security decision from a frame; it
 *    refetches authoritative state over HTTP on (re)connect.
 *  - Reconnect with exponential backoff + jitter.
 */
import { env } from "./env";

/** Server-typed, org-scoped event frame. Validated before dispatch (§6). */
export interface ServerEventFrame {
  type: string;
  organization_id: string;
  payload: unknown;
}

export interface SocketHandlers {
  onFrame: (frame: ServerEventFrame) => void;
  /** Fired after (re)connect so callers refetch authoritative HTTP state. */
  onReconnect?: () => void;
  onError?: (error: unknown) => void;
}

export interface SessionSocket {
  close: () => void;
}

function isServerEventFrame(value: unknown): value is ServerEventFrame {
  if (typeof value !== "object" || value === null) return false;
  const frame = value as Record<string, unknown>;
  return (
    typeof frame.type === "string" &&
    typeof frame.organization_id === "string" &&
    "payload" in frame
  );
}

function resolveWsUrl(): string {
  const configured = env.wsUrl;
  if (/^wss?:\/\//i.test(configured)) return configured;
  // Relative path → derive from current origin so cookies stay first-party.
  const origin = window.location.origin.replace(/^http/i, "ws");
  return `${origin}${configured.startsWith("/") ? configured : `/${configured}`}`;
}

/**
 * Open the single per-session socket. Auth rides the handshake: same-origin
 * cookies are sent automatically; if the server negotiates a subprotocol we
 * pass it here. No token is ever placed in the URL.
 */
export function openSessionSocket(
  handlers: SocketHandlers,
  options: { subprotocols?: string[]; maxBackoffMs?: number } = {},
): SessionSocket {
  const maxBackoffMs = options.maxBackoffMs ?? 30_000;
  let attempt = 0;
  let closedByCaller = false;
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const connect = (): void => {
    if (closedByCaller) return;
    socket = options.subprotocols
      ? new WebSocket(resolveWsUrl(), options.subprotocols)
      : new WebSocket(resolveWsUrl());

    socket.onopen = (): void => {
      attempt = 0;
      handlers.onReconnect?.();
    };

    socket.onmessage = (event: MessageEvent<string>): void => {
      try {
        const parsed: unknown = JSON.parse(event.data);
        if (isServerEventFrame(parsed)) {
          handlers.onFrame(parsed);
        }
      } catch (error) {
        handlers.onError?.(error);
      }
    };

    socket.onerror = (event): void => handlers.onError?.(event);

    socket.onclose = (): void => {
      if (closedByCaller) return;
      const backoff = Math.min(maxBackoffMs, 2 ** attempt * 1000);
      const jitter = Math.random() * 0.3 * backoff;
      attempt += 1;
      reconnectTimer = setTimeout(connect, backoff + jitter);
    };
  };

  connect();

  return {
    close(): void {
      closedByCaller = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    },
  };
}
