/**
 * XIOPATH — Toast Notification Component
 * ========================================
 * Renders global toast notifications from toastStore.
 * Features: auto-dismiss with animated progress bar,
 * severity-based styling, smooth entrance/exit animations.
 */
import React, { useEffect, useState } from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';
import useToastStore from '../../stores/toastStore';

const TOAST_ICONS = {
  success: CheckCircle2,
  error:   AlertCircle,
  warning: AlertTriangle,
  info:    Info,
};

const TOAST_COLORS = {
  success: { bg: 'var(--xp-success-bg)', border: 'var(--xp-success)', color: 'var(--xp-success)' },
  error:   { bg: 'var(--xp-danger-bg)',  border: 'var(--xp-danger)',  color: 'var(--xp-danger)' },
  warning: { bg: 'var(--xp-warning-bg)', border: 'var(--xp-warning)', color: 'var(--xp-warning)' },
  info:    { bg: 'var(--xp-info-bg)',    border: 'var(--xp-info)',    color: 'var(--xp-info)' },
};

function ToastItem({ toast, onDismiss }) {
  const [exiting, setExiting] = useState(false);
  const Icon = TOAST_ICONS[toast.type] || Info;
  const colors = TOAST_COLORS[toast.type] || TOAST_COLORS.info;

  const handleDismiss = () => {
    setExiting(true);
    setTimeout(() => onDismiss(toast.id), 200);
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--xp-space-3)',
        padding: '14px 16px',
        background: 'var(--xp-bg-elevated)',
        border: `1px solid ${colors.border}40`,
        borderLeft: `3px solid ${colors.border}`,
        borderRadius: 'var(--xp-radius-lg)',
        boxShadow: 'var(--xp-shadow-xl)',
        minWidth: '320px',
        maxWidth: '440px',
        backdropFilter: 'blur(12px)',
        animation: exiting
          ? 'xp-slide-in-right 200ms ease reverse forwards'
          : 'xp-slide-in-right 300ms var(--xp-ease-spring) forwards',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <Icon size={18} style={{ color: colors.color, flexShrink: 0, marginTop: '1px' }} />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--xp-text-sm)',
          fontWeight: 'var(--xp-weight-medium)',
          color: 'var(--xp-text-primary)',
          lineHeight: 'var(--xp-leading-normal)',
          wordBreak: 'break-word',
        }}>
          {toast.message}
        </div>
      </div>

      <button
        onClick={handleDismiss}
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--xp-text-muted)',
          cursor: 'pointer',
          padding: '2px',
          flexShrink: 0,
          display: 'flex',
          borderRadius: 'var(--xp-radius-sm)',
          transition: 'color 150ms ease',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--xp-text-primary)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--xp-text-muted)')}
      >
        <X size={14} />
      </button>

      {/* Progress bar for auto-dismiss */}
      {toast.duration > 0 && (
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            height: '2px',
            background: colors.color,
            borderRadius: '0 0 0 var(--xp-radius-lg)',
            animation: `xp-toast-progress ${toast.duration}ms linear forwards`,
            opacity: 0.6,
          }}
        />
      )}
    </div>
  );
}

export default function Toast() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 'var(--xp-space-4)',
        right: 'var(--xp-space-4)',
        zIndex: 'var(--xp-z-toast)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--xp-space-2)',
        pointerEvents: 'none',
      }}
    >
      {toasts.map((toast) => (
        <div key={toast.id} style={{ pointerEvents: 'auto' }}>
          <ToastItem toast={toast} onDismiss={removeToast} />
        </div>
      ))}
    </div>
  );
}
