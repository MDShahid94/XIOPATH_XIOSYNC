/**
 * XIOPATH — v2 API Client
 * ========================
 * Wraps all v5.0 endpoints (actors, types, orgs, workflows, knowledge).
 * Self-contained interceptors — no fragile cross-reference to v1 handlers.
 */
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const apiV2 = axios.create({
  baseURL: `${API_URL}/v2`,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT token on every request
apiV2.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('xp_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Unified error handling
apiV2.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status, data } = error.response;

      if (status === 401) {
        localStorage.removeItem('xp_token');
        localStorage.removeItem('xp_user');
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      }

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

// v1 reference for health endpoint only (remains on v1)
import api from './api';

// ═════════════════════════════════════════════════════════════
// ACTORS
// ═════════════════════════════════════════════════════════════

export const actorsAPI = {
  list:   (params = {})     => apiV2.get('/actors', { params }),
  get:    (id)              => apiV2.get(`/actors/${id}`),
  create: (data)            => apiV2.post('/actors', data),
  update: (id, data)        => apiV2.patch(`/actors/${id}`, data),
  delete: (id)              => apiV2.delete(`/actors/${id}`),
  edges:  (id)              => apiV2.get(`/actors/${id}/edges`),
  ops:    (id)              => apiV2.get(`/actors/${id}/operations`),
};

// ═════════════════════════════════════════════════════════════
// TYPE REGISTRY
// ═════════════════════════════════════════════════════════════

export const typesAPI = {
  list:     (category)      => apiV2.get('/types', { params: { category } }),
  get:      (category, name)=> apiV2.get(`/types/${category}/${name}`),
  register: (data)          => apiV2.post('/types', data),
  deprecate:(category, name)=> apiV2.patch(`/types/${category}/${name}`),
  delete:   (category, name)=> apiV2.delete(`/types/${category}/${name}`),
  validateSchema: (data)    => apiV2.post('/types/validate-action-spec', data),
};

// ═════════════════════════════════════════════════════════════
// ORGANIZATIONS
// ═════════════════════════════════════════════════════════════

export const orgsAPI = {
  list:       ()            => apiV2.get('/orgs'),
  get:        (id)          => apiV2.get(`/orgs/${id}`),
  create:     (data)        => apiV2.post('/orgs', data),
  update:     (id, data)    => apiV2.patch(`/orgs/${id}`, data),
  delete:     (id)          => apiV2.delete(`/orgs/${id}`),
  members:    (id)          => apiV2.get(`/orgs/${id}/members`),
  addMember:  (id, data)    => apiV2.post(`/orgs/${id}/members`, data),
  removeMember: (orgId, actorId) => apiV2.delete(`/orgs/${orgId}/members/${actorId}`),
};

// ═════════════════════════════════════════════════════════════
// WORKFLOWS
// ═════════════════════════════════════════════════════════════

export const workflowsAPI = {
  list:       (params = {}) => apiV2.get('/workflows', { params }),
  get:        (id)          => apiV2.get(`/workflows/${id}`),
  create:     (data)        => apiV2.post('/workflows', data),
  update:     (id, data)    => apiV2.patch(`/workflows/${id}`, data),
  delete:     (id)          => apiV2.delete(`/workflows/${id}`),
  activate:   (id)          => apiV2.post(`/workflows/${id}/activate`),
  fork:       (id, data)    => apiV2.post(`/workflows/${id}/fork`, data),
  execute:    (id, data={}) => apiV2.post(`/workflows/${id}/execute`, data),
  executions: (id, params)  => apiV2.get(`/workflows/${id}/executions`, { params }),
  stats:      (id)          => apiV2.get(`/workflows/${id}/stats`),
  getExecution:    (id)     => apiV2.get(`/executions/${id}`),
  pauseExecution:  (id)     => apiV2.post(`/executions/${id}/pause`),
  resumeExecution: (id)     => apiV2.post(`/executions/${id}/resume`),
  cancelExecution: (id)     => apiV2.post(`/executions/${id}/cancel`),
};

// ═════════════════════════════════════════════════════════════
// HEALTH (remains on v1)
// ═════════════════════════════════════════════════════════════

export const healthAPI = {
  check: () => api.get('/health'),
};

// ═════════════════════════════════════════════════════════════
// MEMORY (v2)
// ═════════════════════════════════════════════════════════════

export const memoryAPI = {
  search: (query) => apiV2.get('/memory/search', { params: { query } }),
  graph: (url, intent) => apiV2.get('/memory/graph', { params: { url, intent } }),
};

export default apiV2;
