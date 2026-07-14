/**
 * XIOPATH — WebSocket Store (Zustand)
 * ======================================
 * Manages a persistent WebSocket connection for real-time updates.
 * Supports channel-based subscriptions and auto-reconnect.
 */
import { create } from 'zustand';

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/api/v1/ws/dashboard';

const MAX_RECONNECT_DELAY = 30000;

const useWsStore = create((set, get) => ({
  // ─── State ─────────────────────────────────────────────────
  ws: null,
  status: 'disconnected', // 'connecting' | 'connected' | 'disconnected' | 'error'
  reconnectAttempts: 0,
  listeners: new Map(), // channel -> Set of callbacks

  // ─── Actions ───────────────────────────────────────────────

  /** Connect to the WebSocket server */
  connect: () => {
    const { ws, status } = get();
    if (ws && (status === 'connected' || status === 'connecting')) return;

    const token = localStorage.getItem('xp_token');
    if (!token) return;

    set({ status: 'connecting' });

    const wsUrl = `${WS_BASE}?token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      set({ ws: socket, status: 'connected', reconnectAttempts: 0 });
      console.log('[XIOPATH WS] Connected');
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const channel = data.channel || 'default';
        const { listeners } = get();
        const channelListeners = listeners.get(channel);
        if (channelListeners) {
          channelListeners.forEach((cb) => cb(data.payload || data));
        }
        // Also broadcast to wildcard listeners
        const wildcardListeners = listeners.get('*');
        if (wildcardListeners) {
          wildcardListeners.forEach((cb) => cb(data));
        }
      } catch (e) {
        console.error('[XIOPATH WS] Failed to parse message:', e);
      }
    };

    socket.onclose = (event) => {
      set({ ws: null, status: 'disconnected' });
      console.log('[XIOPATH WS] Disconnected:', event.code, event.reason);

      // Auto-reconnect with exponential backoff
      if (!event.wasClean) {
        const { reconnectAttempts } = get();
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
        set({ reconnectAttempts: reconnectAttempts + 1 });
        console.log(`[XIOPATH WS] Reconnecting in ${delay}ms...`);
        setTimeout(() => get().connect(), delay);
      }
    };

    socket.onerror = (error) => {
      console.error('[XIOPATH WS] Error:', error);
      set({ status: 'error' });
    };

    set({ ws: socket });
  },

  /** Disconnect from the WebSocket server */
  disconnect: () => {
    const { ws } = get();
    if (ws) {
      ws.close(1000, 'User disconnect');
      set({ ws: null, status: 'disconnected', reconnectAttempts: 0 });
    }
  },

  /** Subscribe to a channel */
  subscribe: (channel, callback) => {
    const { listeners } = get();
    if (!listeners.has(channel)) {
      listeners.set(channel, new Set());
    }
    listeners.get(channel).add(callback);
    set({ listeners: new Map(listeners) });

    // Return unsubscribe function
    return () => {
      listeners.get(channel)?.delete(callback);
      if (listeners.get(channel)?.size === 0) {
        listeners.delete(channel);
      }
      set({ listeners: new Map(listeners) });
    };
  },

  /** Send a message through the WebSocket */
  send: (data) => {
    const { ws, status } = get();
    if (ws && status === 'connected') {
      ws.send(JSON.stringify(data));
    } else {
      console.warn('[XIOPATH WS] Cannot send — not connected');
    }
  },
}));

export default useWsStore;
