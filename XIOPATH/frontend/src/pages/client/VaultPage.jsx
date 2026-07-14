/**
 * XIOPATH — Security Vault Page
 * ================================
 * Full CRUD management for encrypted credentials.
 * Add, edit, delete, and categorize vault secrets.
 */
import React, { useState, useEffect } from 'react';
import {
  KeyRound, Plus, Pencil, Trash2, Eye, EyeOff, Search,
  Loader2, RefreshCw, Lock, ShieldCheck, X, Save, Copy, Check
} from 'lucide-react';
import api from '../../lib/api';
import ModalPortal from '../../components/ModalPortal';
import useToastStore from '../../stores/toastStore';

export default function VaultPage() {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingKey, setEditingKey] = useState(null);
  const [revealedKeys, setRevealedKeys] = useState(new Set());
  const [copiedKey, setCopiedKey] = useState(null);
  const addToast = useToastStore((s) => s.addToast);

  // Form state
  const [formKey, setFormKey] = useState('');
  const [formValue, setFormValue] = useState('');
  const [formLoading, setFormLoading] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => { fetchKeys(); }, []);

  const fetchKeys = async () => {
    setLoading(true);
    try {
      const res = await api.get('/vault/keys');
      setKeys((res.data.keys || []).map((k) => typeof k === 'string' ? { key: k, masked: true } : k));
    } catch {
      setKeys([]);
    }
    setLoading(false);
  };

  const handleAdd = async () => {
    if (!formKey || !formValue) { setFormError('Both key and value are required.'); return; }
    setFormLoading(true);
    setFormError('');
    try {
      await api.post('/vault/add', { key: formKey, value: formValue });
      addToast('Secret added successfully', 'success');
      setShowAddModal(false);
      setFormKey('');
      setFormValue('');
      fetchKeys();
    } catch (err) {
      setFormError(err.message);
      addToast(err.message, 'error');
    }
    setFormLoading(false);
  };

  const handleUpdate = async () => {
    if (!formValue) { setFormError('Value is required.'); return; }
    setFormLoading(true);
    setFormError('');
    try {
      await api.put(`/vault/${editingKey}`, { value: formValue });
      addToast('Secret updated successfully', 'success');
      setEditingKey(null);
      setFormValue('');
      fetchKeys();
    } catch (err) {
      setFormError(err.message);
      addToast(err.message, 'error');
    }
    setFormLoading(false);
  };

  const handleDelete = async (key) => {
    // Basic confirm since we don't have a confirmation modal component yet
    if (!window.confirm(`Are you sure you want to delete "${key}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/vault/${key}`);
      addToast('Secret deleted', 'success');
      fetchKeys();
    } catch (err) {
      addToast(`Delete failed: ${err.message}`, 'error');
    }
  };

  const copyReference = (key) => {
    navigator.clipboard.writeText(`vault://${key}`);
    setCopiedKey(key);
    addToast('Reference copied to clipboard', 'info');
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const filtered = keys.filter((k) =>
    !searchTerm || k.key.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const categorizeKey = (key) => {
    const lower = key.toLowerCase();
    if (lower.includes('password') || lower.includes('pass')) return { label: 'Password', color: 'var(--xp-danger)' };
    if (lower.includes('api') || lower.includes('key') || lower.includes('token')) return { label: 'API Key', color: 'var(--xp-purple)' };
    if (lower.includes('email') || lower.includes('mail')) return { label: 'Credential', color: 'var(--xp-cyan)' };
    return { label: 'Secret', color: 'var(--xp-text-muted)' };
  };

  return (
    <div className="xp-animate-fade-in">
      {/* ─── Page Header ──────────────────────────── */}
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Security Vault</h1>
          <p className="xp-page-subtitle">Manage encrypted credentials for workflow injection</p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--xp-space-2)' }}>
          <button className="xp-btn xp-btn-secondary" onClick={fetchKeys} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'xp-animate-spin' : ''} />
          </button>
          <button className="xp-btn xp-btn-primary" onClick={() => { setShowAddModal(true); setFormKey(''); setFormValue(''); setFormError(''); }}>
            <Plus size={14} /> Add Secret
          </button>
        </div>
      </div>

      {/* ─── Stats ────────────────────────────────── */}
      <div className="xp-grid xp-grid-3" style={{ marginBottom: 'var(--xp-space-5)' }}>
        {[
          { label: 'Total Secrets', value: keys.length, icon: KeyRound, color: 'var(--xp-cyan)' },
          { label: 'API Keys', value: keys.filter(k => categorizeKey(k.key).label === 'API Key').length, icon: Lock, color: 'var(--xp-purple)' },
          { label: 'Encrypted', value: keys.length, icon: ShieldCheck, color: 'var(--xp-success)' },
        ].map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className="xp-card">
              <div className="xp-stat">
                <span className="xp-stat-label">{stat.label}</span>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span className="xp-stat-value">{loading ? '—' : stat.value}</span>
                  <Icon size={20} style={{ color: stat.color }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ─── Search ───────────────────────────────── */}
      <div style={{ position: 'relative', marginBottom: 'var(--xp-space-4)' }}>
        <Search size={14} style={{
          position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)',
          color: 'var(--xp-text-muted)',
        }} />
        <input
          className="xp-input"
          placeholder="Search secrets by name..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ paddingLeft: '36px' }}
        />
      </div>

      {/* ─── Vault Table ──────────────────────────── */}
      {loading ? (
        <div className="xp-card xp-stagger">
          {[1, 2, 3].map((i) => (
            <div key={i} className="xp-skeleton" style={{ height: '48px', marginBottom: 'var(--xp-space-3)' }} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="xp-card">
          <div className="xp-empty">
            <KeyRound size={40} className="xp-empty-icon" />
            <div className="xp-empty-title">{searchTerm ? 'No matching secrets' : 'Vault is empty'}</div>
            <div className="xp-empty-desc">
              {searchTerm ? 'Try a different search term.' : 'Add your first secret to start using vault:// references in workflows.'}
            </div>
          </div>
        </div>
      ) : (
        <div className="xp-card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="xp-table">
            <thead>
              <tr>
                <th className="xp-th">Key Name</th>
                <th className="xp-th">Category</th>
                <th className="xp-th">Reference</th>
                <th className="xp-th" style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const cat = categorizeKey(item.key);
                return (
                  <tr key={item.key} className="xp-tr-interactive">
                    <td className="xp-td">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
                        <Lock size={14} style={{ color: 'var(--xp-text-muted)' }} />
                        <span style={{ fontWeight: 'var(--xp-weight-medium)' }}>{item.key}</span>
                      </div>
                    </td>
                    <td className="xp-td">
                      <span className="xp-badge xp-badge-neutral" style={{ color: cat.color }}>
                        {cat.label}
                      </span>
                    </td>
                    <td className="xp-td">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
                        <code style={{
                          fontSize: 'var(--xp-text-xs)',
                          padding: '2px 6px',
                          background: 'var(--xp-bg-base)',
                          borderRadius: 'var(--xp-radius-sm)',
                          border: '1px solid var(--xp-border-subtle)',
                          color: 'var(--xp-cyan)',
                        }}>
                          vault://{item.key}
                        </code>
                        <button
                          className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-xs"
                          onClick={() => copyReference(item.key)}
                          data-tooltip={copiedKey === item.key ? 'Copied!' : 'Copy reference'}
                        >
                          {copiedKey === item.key ? <Check size={12} style={{ color: 'var(--xp-success)' }} /> : <Copy size={12} />}
                        </button>
                      </div>
                    </td>
                    <td className="xp-td" style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end' }}>
                        <button
                          className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm"
                          data-tooltip="Edit"
                          onClick={() => { setEditingKey(item.key); setFormValue(''); setFormError(''); }}
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm"
                          data-tooltip="Delete"
                          onClick={() => handleDelete(item.key)}
                          style={{ color: 'var(--xp-danger)' }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ─── Add Modal ────────────────────────────── */}
      {(showAddModal || editingKey) && (
        <ModalPortal>
          <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--xp-space-4)' }}>
            <div onClick={() => { setShowAddModal(false); setEditingKey(null); }}
              style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
              className="xp-animate-fade-in"
            />
            <div style={{
              position: 'relative',
              background: 'var(--xp-bg-elevated)', border: '1px solid var(--xp-border-default)',
              borderRadius: 'var(--xp-radius-xl)', padding: 'var(--xp-space-6)',
              width: '100%', maxWidth: '420px', boxShadow: 'var(--xp-shadow-xl)',
            }} className="xp-animate-scale-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-5)' }}>
              <h3 style={{ margin: 0 }}>{editingKey ? `Update: ${editingKey}` : 'Add Secret'}</h3>
              <button className="xp-btn xp-btn-ghost xp-btn-icon" onClick={() => { setShowAddModal(false); setEditingKey(null); }}>
                <X size={18} />
              </button>
            </div>

            {formError && (
              <div style={{
                padding: 'var(--xp-space-3)', background: 'var(--xp-danger-bg)',
                border: '1px solid rgba(239,68,68,0.2)', borderRadius: 'var(--xp-radius-md)',
                marginBottom: 'var(--xp-space-4)', fontSize: 'var(--xp-text-sm)', color: 'var(--xp-danger)',
              }}>
                {formError}
              </div>
            )}

            {!editingKey && (
              <div className="xp-field" style={{ marginBottom: 'var(--xp-space-4)' }}>
                <label className="xp-label">Key Name</label>
                <input className="xp-input" placeholder="e.g. google_password"
                  value={formKey} onChange={(e) => setFormKey(e.target.value)}
                />
              </div>
            )}

            <div className="xp-field" style={{ marginBottom: 'var(--xp-space-5)' }}>
              <label className="xp-label">{editingKey ? 'New Value' : 'Value'}</label>
              <input className="xp-input" type="password"
                placeholder="Enter secret value..."
                value={formValue} onChange={(e) => setFormValue(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', gap: 'var(--xp-space-3)', justifyContent: 'flex-end' }}>
              <button className="xp-btn xp-btn-secondary" onClick={() => { setShowAddModal(false); setEditingKey(null); }}>
                Cancel
              </button>
              <button className="xp-btn xp-btn-primary" disabled={formLoading}
                onClick={editingKey ? handleUpdate : handleAdd}
              >
                {formLoading ? <Loader2 size={14} className="xp-animate-spin" /> : <Save size={14} />}
                {editingKey ? 'Update' : 'Save'}
              </button>
            </div>
          </div>
          </div>
        </ModalPortal>
      )}
    </div>
  );
}
