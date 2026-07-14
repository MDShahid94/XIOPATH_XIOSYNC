/**
 * XIOPATH — Centralized API Client
 * ==================================
 * Axios instance with auth interceptor, error handling, and auto token refresh.
 */
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Request Interceptor: Attach JWT ─────────────────────────
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('xp_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Response Interceptor: Unified Error Handling ────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status, data } = error.response;

      // Auto-logout on 401
      if (status === 401) {
        localStorage.removeItem('xp_token');
        localStorage.removeItem('xp_user');
        // Only redirect if not already on login
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      }

      // Extract error message
      const message = data?.detail
        ? typeof data.detail === 'string'
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map(d => `${d.loc?.join('.')}: ${d.msg}`).join(', ')
            : 'An error occurred'
        : data?.error?.message || error.message;

      return Promise.reject(new Error(message));
    }

    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new Error('Request timed out. Please try again.'));
    }

    return Promise.reject(new Error('Unable to connect to the server.'));
  }
);

export { API_BASE };
export default api;
