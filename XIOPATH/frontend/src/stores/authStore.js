/**
 * XIOPATH — Auth Store (Zustand)
 * ================================
 * Manages authentication state with localStorage persistence.
 */
import { create } from 'zustand';
import api from '../lib/api';

const useAuthStore = create((set, get) => ({
  // ─── State ─────────────────────────────────────────────────
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true, // Loading until hydration completes

  // ─── Actions ───────────────────────────────────────────────

  /** Revalidate any persisted bearer token before trusting identity or role claims. */
  hydrate: async () => {
    const token = localStorage.getItem('xp_token');

    if (!token) {
      set({ user: null, token: null, isAuthenticated: false, isLoading: false });
      return;
    }

    try {
      const { data } = await api.get('/auth/me');
      const user = {
        id: data.actor_id,
        username: data.username,
        role: data.role,
      };
      localStorage.setItem('xp_user', JSON.stringify(user));
      set({ user, token, isAuthenticated: true, isLoading: false });
    } catch {
      localStorage.removeItem('xp_token');
      localStorage.removeItem('xp_user');
      set({ user: null, token: null, isAuthenticated: false, isLoading: false });
    }
  },

  /** Login with username/password */
  login: async (username, password) => {
    const res = await api.post('/auth/login', { username, password });
    const { token, role, username: uname } = res.data;

    const user = { username: uname, role, id: res.data.sub };

    localStorage.setItem('xp_token', token);
    localStorage.setItem('xp_user', JSON.stringify(user));

    set({ user, token, isAuthenticated: true });
    return user;
  },

  /** Public signup always creates a client account; roles are server-managed. */
  signup: async (username, password) => {
    await api.post('/auth/signup', { username, password });
  },

  /** Logout and clear state */
  logout: () => {
    localStorage.removeItem('xp_token');
    localStorage.removeItem('xp_user');
    set({ user: null, token: null, isAuthenticated: false });
  },

  /** Check if user has a specific role */
  hasRole: (role) => {
    const { user } = get();
    return user?.role === role;
  },

  /** Get the user's display initials */
  getInitials: () => {
    const { user } = get();
    if (!user?.username) return '?';
    return user.username.slice(0, 2).toUpperCase();
  },
}));

export default useAuthStore;
