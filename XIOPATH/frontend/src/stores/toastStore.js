/**
 * XIOPATH — Toast Notification Store
 * =====================================
 * Zustand store for global toast notifications.
 * Replaces all alert() / window.confirm() calls.
 */
import { create } from 'zustand';

let toastIdCounter = 0;

const useToastStore = create((set, get) => ({
  toasts: [],

  /**
   * Add a toast notification.
   * @param {string} message - The toast message
   * @param {'success'|'error'|'warning'|'info'} type - Severity level
   * @param {number} duration - Auto-dismiss duration in ms (0 = persistent)
   */
  addToast: (message, type = 'info', duration = 4000) => {
    const id = ++toastIdCounter;
    const toast = { id, message, type, duration, createdAt: Date.now() };

    set((state) => ({
      toasts: [...state.toasts, toast],
    }));

    if (duration > 0) {
      setTimeout(() => {
        get().removeToast(id);
      }, duration);
    }

    return id;
  },

  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },

  clearAll: () => set({ toasts: [] }),
}));

export default useToastStore;
