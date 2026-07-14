/**
 * XIOPATH — Agent & Environment Store (Phase F.4)
 * ==================================================
 * Zustand store for managing agents, environments, and their lifecycle.
 */
import { create } from 'zustand';
import apiV2 from '../lib/api-v2';
import api from '../lib/api';

const useAgentStore = create((set, get) => ({
  // State
  agents: [],
  environments: [],
  currentAgent: null,
  loading: false,
  error: null,

  // ─── Agents (Ontology v2 API) ──────────────────────
  fetchAgents: async () => {
    set({ loading: true, error: null });
    try {
      const { data } = await apiV2.get('/agents');
      set({ agents: data.agents || data || [], loading: false });
    } catch (err) {
      // Graceful fallback if ontology tables don't exist
      set({ agents: [], error: null, loading: false });
    }
  },

  getAgent: async (agentId) => {
    set({ loading: true, error: null });
    try {
      const { data } = await apiV2.get(`/agents/${agentId}`);
      set({ currentAgent: data, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  // ─── Environments ──────────────────────────────────
  fetchEnvironments: async () => {
    set({ loading: true, error: null });
    try {
      const { data } = await api.get('/marketplace/my/installed');
      set({ environments: data.environments || [], loading: false });
    } catch (err) {
      set({ environments: [], error: null, loading: false });
    }
  },

  deleteEnvironment: async (envId) => {
    try {
      await api.delete(`/environments/${envId}`);
      set((s) => ({
        environments: s.environments.filter((e) => e.id !== envId),
      }));
    } catch (err) {
      set({ error: err.message });
    }
  },

  // ─── Reset ─────────────────────────────────────────
  clearError: () => set({ error: null }),
  clearCurrent: () => set({ currentAgent: null }),
}));

export default useAgentStore;
