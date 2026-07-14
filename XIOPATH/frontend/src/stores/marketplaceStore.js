/**
 * XIOPATH — Marketplace Store (Phase F.3)
 * =========================================
 * Zustand store for marketplace state — browse, search, install, review.
 */
import { create } from 'zustand';
import api from '../lib/api';

const useMarketplaceStore = create((set, get) => ({
  // State
  listings: [],
  currentListing: null,
  searchResults: [],
  myPublished: [],
  myInstalled: [],
  total: 0,
  loading: false,
  error: null,
  query: '',
  category: '',
  page: 0,
  pageSize: 12,

  // ─── Browse ────────────────────────────────────────
  browse: async (category = '', offset = 0) => {
    set({ loading: true, error: null, category });
    try {
      const params = { limit: get().pageSize, offset };
      if (category) params.category = category;
      const { data } = await api.get('/marketplace/browse', { params });
      set({
        listings: data.listings || [],
        total: data.total || 0,
        page: offset,
        loading: false,
      });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  // ─── Search ────────────────────────────────────────
  search: async (q) => {
    set({ loading: true, error: null, query: q });
    try {
      const { data } = await api.get('/marketplace/search', { params: { q, limit: 20 } });
      set({ searchResults: data.listings || [], loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  // ─── Get Detail ────────────────────────────────────
  getDetail: async (listingId) => {
    set({ loading: true, error: null });
    try {
      const { data } = await api.get(`/marketplace/${listingId}`);
      set({ currentListing: data, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false, currentListing: null });
    }
  },

  // ─── Install ───────────────────────────────────────
  install: async (listingId) => {
    set({ loading: true, error: null });
    try {
      const { data } = await api.post(`/marketplace/${listingId}/install`);
      // Update install count in listings
      set((s) => ({
        loading: false,
        listings: s.listings.map((l) =>
          l.id === listingId ? { ...l, install_count: (l.install_count || 0) + 1 } : l
        ),
      }));
      return data;
    } catch (err) {
      set({ error: err.message, loading: false });
      throw err;
    }
  },

  // ─── Review ────────────────────────────────────────
  review: async (listingId, rating, comment) => {
    try {
      await api.post(`/marketplace/${listingId}/review`, { rating, comment });
      // Refresh detail
      get().getDetail(listingId);
    } catch (err) {
      set({ error: err.message });
    }
  },

  // ─── My Listings ───────────────────────────────────
  fetchMyPublished: async () => {
    try {
      const { data } = await api.get('/marketplace/my/published');
      set({ myPublished: data.listings || [] });
    } catch (err) {
      set({ error: err.message });
    }
  },

  fetchMyInstalled: async () => {
    try {
      const { data } = await api.get('/marketplace/my/installed');
      set({ myInstalled: data.environments || [] });
    } catch (err) {
      set({ error: err.message });
    }
  },

  // ─── Reset ─────────────────────────────────────────
  clearSearch: () => set({ searchResults: [], query: '' }),
  clearError: () => set({ error: null }),
}));

export default useMarketplaceStore;
