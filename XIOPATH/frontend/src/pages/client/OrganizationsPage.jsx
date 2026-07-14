/**
 * XIOPATH — Organizations Page (v5.0)
 * =====================================
 * Multi-tenant organization management with member roles.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { orgsAPI } from '../../lib/api-v2';
import ModalPortal from '../../components/ModalPortal';
import useToastStore from '../../stores/toastStore';
import { Building2, Users, Clock, Loader2, X } from 'lucide-react';

const PLAN_BADGES = {
  free:       { bg: 'var(--xp-text-muted)', label: 'Free' },
  pro:        { bg: 'var(--xp-purple)', label: 'Pro' },
  enterprise: { bg: 'var(--xp-warning)', label: 'Enterprise' },
};

const ROLE_COLORS = {
  owner:  'var(--xp-danger)',
  admin:  'var(--xp-warning)',
  member: 'var(--xp-blue)',
  viewer: 'var(--xp-text-muted)',
};

export default function OrganizationsPage() {
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrg, setSelectedOrg] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const addToast = useToastStore((s) => s.addToast);

  const fetchOrgs = useCallback(async () => {
    try {
      setLoading(true);
      const res = await orgsAPI.list();
      setOrgs(res.data?.organizations || res.data || []);
    } catch (err) {
      addToast('Failed to load organizations: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchOrgs(); }, [fetchOrgs]);

  return (
    <div className="xp-animate-fade-in" style={{ padding: 'var(--xp-space-6)' }}>
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title" style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
            <Building2 size={28} style={{ color: 'var(--xp-cyan)' }} /> Organizations
          </h1>
          <p className="xp-page-subtitle">
            {orgs.length} organizations
          </p>
        </div>
        <button className="xp-btn xp-btn-primary" onClick={() => setShowCreate(true)}>+ Create Org</button>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--xp-space-12)', color: 'var(--xp-text-muted)' }}>
          <div className="xp-animate-spin" style={{ width: 24, height: 24, border: '2px solid var(--xp-border-subtle)', borderTop: '2px solid var(--xp-cyan)', borderRadius: '50%' }} />
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: 'var(--xp-space-4)' }}>
          {orgs.map((org) => {
            const plan = PLAN_BADGES[org.plan] || PLAN_BADGES.free;
            return (
              <div key={org.id} className="xp-card" style={{ padding: 'var(--xp-space-4)', cursor: 'pointer' }}
                onClick={() => setSelectedOrg(org)}
                onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--xp-shadow-lg)'; }}
                onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ fontSize: 'var(--xp-text-lg)', fontWeight: 600, color: 'var(--xp-text-primary)' }}>
                      {org.name}
                    </div>
                    <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', marginTop: 4 }}>
                      {org.description || 'No description'}
                    </div>
                  </div>
                  <span style={{
                    padding: '2px 10px', borderRadius: 'var(--xp-radius-full)',
                    background: `${plan.bg}20`, color: plan.bg,
                    fontSize: 'var(--xp-text-xs)', fontWeight: 600,
                  }}>{plan.label}</span>
                </div>
                <div style={{ display: 'flex', gap: 'var(--xp-space-4)', marginTop: 'var(--xp-space-4)', fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-secondary)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Users size={12} /> {org.max_actors || 50} actors max</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Clock size={12} /> {new Date(org.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && orgs.length === 0 && (
        <div className="xp-empty xp-animate-fade-in">
          <Building2 size={48} className="xp-empty-icon" />
          <div className="xp-empty-title">No organizations</div>
          <div className="xp-empty-desc">Create an organization to collaborate with your team.</div>
        </div>
      )}

      {showCreate && (
        <CreateOrgModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); fetchOrgs(); }} />
      )}

      {selectedOrg && (
        <OrgDetail org={selectedOrg} onClose={() => setSelectedOrg(null)} />
      )}
    </div>
  );
}


function OrgDetail({ org, onClose }) {
  const [members, setMembers] = useState([]);
  useEffect(() => {
    orgsAPI.members(org.id).then(r => setMembers(r.data?.members || [])).catch(() => {});
  }, [org.id]);

  return (
    <ModalPortal>
      <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', justifyContent: 'flex-end' }}>
        <div onClick={onClose}
             style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
             className="xp-animate-fade-in" />
        
        <div style={{
          position: 'relative', width: 420, height: '100%',
          background: 'var(--xp-bg-surface)', borderLeft: '1px solid var(--xp-border-default)',
          padding: 'var(--xp-space-6)', overflowY: 'auto', boxShadow: 'var(--xp-shadow-xl)',
        }} className="xp-animate-slide-right">
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--xp-space-4)' }}>
            <h2 style={{ margin: 0, fontSize: 'var(--xp-text-lg)', fontWeight: 700, color: 'var(--xp-text-primary)' }}>{org.name}</h2>
            <button onClick={onClose} className="xp-btn xp-btn-ghost xp-btn-icon" style={{ cursor: 'pointer' }}><X size={18} /></button>
          </div>
          <p style={{ color: 'var(--xp-text-secondary)', fontSize: 'var(--xp-text-sm)', marginBottom: 'var(--xp-space-4)' }}>{org.description || '—'}</p>

          <h3 style={{ fontSize: 'var(--xp-text-sm)', fontWeight: 600, marginBottom: 'var(--xp-space-2)', color: 'var(--xp-text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Users size={14} /> Members ({members.length})
          </h3>
          {members.map((m, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 12px', background: 'var(--xp-bg-subtle)', borderRadius: 'var(--xp-radius-md)',
              marginBottom: 6,
            }}>
              <span style={{ fontSize: 'var(--xp-text-sm)', fontFamily: 'var(--xp-font-mono)', color: 'var(--xp-text-primary)' }}>
                {(m.actor_id || '').slice(0, 12)}...
              </span>
              <span style={{
                padding: '2px 8px', borderRadius: 'var(--xp-radius-full)',
                fontSize: '10px', fontWeight: 600,
                background: `${ROLE_COLORS[m.role] || '#6b7280'}20`,
                color: ROLE_COLORS[m.role] || '#6b7280',
              }}>{m.role}</span>
            </div>
          ))}
        </div>
      </div>
    </ModalPortal>
  );
}


function CreateOrgModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: '', description: '', plan: 'free' });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSubmitting(true);
    try {
      await orgsAPI.create(form);
      useToastStore.getState().addToast('Organization created', 'success');
      onCreated();
    } catch (err) {
      useToastStore.getState().addToast('Failed to create organization: ' + err.message, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalPortal>
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200 }} onClick={onClose}>
      <div style={{ background: 'var(--xp-bg-surface)', borderRadius: 'var(--xp-radius-xl)', padding: 'var(--xp-space-6)', width: 400, border: '1px solid var(--xp-border-default)' }} onClick={e => e.stopPropagation()} className="xp-animate-fade-in">
        <h2 style={{ margin: '0 0 var(--xp-space-4)', fontSize: 'var(--xp-text-lg)', fontWeight: 700, color: 'var(--xp-text-primary)' }}>Create Organization</h2>
        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 'var(--xp-space-3)' }}>
          <div className="xp-field">
            <label className="xp-label">Organization Name</label>
            <input className="xp-input" placeholder="e.g. Acme Corp" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
          </div>
          <div className="xp-field">
            <label className="xp-label">Description (optional)</label>
            <input className="xp-input" placeholder="Brief description" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>
          <div className="xp-field">
            <label className="xp-label">Plan</label>
            <select className="xp-select" value={form.plan} onChange={e => setForm(f => ({ ...f, plan: e.target.value }))}>
              <option value="free">Free (50 actors)</option>
              <option value="pro">Pro (500 actors)</option>
              <option value="enterprise">Enterprise (unlimited)</option>
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
            <button type="button" className="xp-btn xp-btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="xp-btn xp-btn-primary" disabled={submitting}>
              {submitting ? <Loader2 size={14} className="xp-animate-spin" /> : null}
              {submitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
      </div>
    </ModalPortal>
  );
}
