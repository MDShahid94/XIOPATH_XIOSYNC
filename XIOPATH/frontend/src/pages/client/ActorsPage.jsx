/**
 * XIOPATH — Actors Page (v5.0)
 * ==============================
 * Lists all actors in the system with type badges, status indicators,
 * and edge relationship visualization.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { actorsAPI, typesAPI } from '../../lib/api-v2';
import ModalPortal from '../../components/ModalPortal';
import useToastStore from '../../stores/toastStore';
import { Users, Bot, Cpu, Trash2 } from 'lucide-react';

const ACTOR_TYPE_COLORS = {
  human:   { bg: 'var(--xp-cyan)',   label: 'Human',   icon: Users },
  ai:      { bg: 'var(--xp-purple)', label: 'AI',      icon: Bot },
  compute: { bg: 'var(--xp-blue)',   label: 'Compute', icon: Cpu },
};

const STATUS_COLORS = {
  active:     'var(--xp-success)',
  inactive:   'var(--xp-text-muted)',
  suspended:  'var(--xp-danger)',
  archived:   'var(--xp-text-disabled)',
};

export default function ActorsPage() {
  const [actors, setActors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedActor, setSelectedActor] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [typeFilter, setTypeFilter] = useState(null);
  const addToast = useToastStore((s) => s.addToast);

  const filteredActors = typeFilter
    ? actors.filter(a => (a.actor_type || a.type) === typeFilter)
    : actors;

  const handleDelete = async (actorId, e) => {
    e.stopPropagation();
    try {
      await actorsAPI.delete(actorId);
      addToast('Actor deleted', 'success');
      fetchActors();
    } catch (err) {
      addToast('Failed to delete: ' + err.message, 'error');
    }
  };

  const fetchActors = useCallback(async () => {
    try {
      setLoading(true);
      const res = await actorsAPI.list();
      setActors(res.data?.actors || res.data || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchActors(); }, [fetchActors]);

  return (
    <div className="xp-animate-fade-in" style={{ padding: 'var(--xp-space-6)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-6)' }}>
        <div>
          <h1 style={{ fontSize: 'var(--xp-text-2xl)', fontWeight: 'var(--xp-weight-bold)', color: 'var(--xp-text-primary)', fontFamily: 'var(--xp-font-display)', margin: 0 }}>
            Actors
          </h1>
          <p style={{ color: 'var(--xp-text-muted)', fontSize: 'var(--xp-text-sm)', marginTop: 'var(--xp-space-1)' }}>
            {actors.length} registered actors in the system
          </p>
        </div>
        <button
          className="xp-btn xp-btn-primary"
          onClick={() => setShowCreateModal(true)}
        >
          + Create Actor
        </button>
      </div>

      {/* Type filter chips (functional) */}
      <div style={{ display: 'flex', gap: 'var(--xp-space-2)', marginBottom: 'var(--xp-space-4)', flexWrap: 'wrap' }}>
        <button
          onClick={() => setTypeFilter(null)}
          className={`xp-badge ${!typeFilter ? 'xp-badge-cyan' : 'xp-badge-neutral'}`}
          style={{ cursor: 'pointer', border: 'none', padding: '6px 12px', fontSize: 'var(--xp-text-xs)' }}
        >
          All ({actors.length})
        </button>
        {Object.entries(ACTOR_TYPE_COLORS).map(([type, { bg, label, icon: TypeIcon }]) => {
          const count = actors.filter(a => (a.actor_type || a.type) === type).length;
          const isActive = typeFilter === type;
          return (
            <button
              key={type}
              onClick={() => setTypeFilter(isActive ? null : type)}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '6px 12px', borderRadius: 'var(--xp-radius-full)',
                background: isActive ? `${bg}25` : 'rgba(255,255,255,0.04)',
                border: `1px solid ${isActive ? bg : 'var(--xp-border-subtle)'}`,
                fontSize: 'var(--xp-text-xs)', color: isActive ? bg : 'var(--xp-text-secondary)',
                fontWeight: 500, cursor: 'pointer', transition: 'all 200ms ease',
              }}
            >
              <TypeIcon size={12} /> {label}
              <span style={{
                background: isActive ? bg : 'var(--xp-bg-elevated)', color: isActive ? 'white' : 'var(--xp-text-muted)',
                borderRadius: 'var(--xp-radius-full)',
                padding: '0 6px', fontSize: '10px', fontWeight: 700, lineHeight: '18px',
              }}>{count}</span>
            </button>
          );
        })}
      </div>

      {/* Error state */}
      {error && (
        <div className="xp-alert xp-alert-error" style={{ marginBottom: 'var(--xp-space-4)' }}>
          ⚠️ {error}
          <button onClick={fetchActors} style={{ marginLeft: 12, textDecoration: 'underline', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--xp-space-12)', color: 'var(--xp-text-muted)' }}>
          <div className="xp-animate-spin" style={{
            width: 24, height: 24, border: '2px solid var(--xp-border-subtle)',
            borderTop: '2px solid var(--xp-cyan)', borderRadius: '50%',
          }} />
        </div>
      )}

      {/* Actor cards grid */}
      {!loading && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: 'var(--xp-space-4)',
        }}>
          {filteredActors.map((actor) => {
            const type = actor.actor_type || actor.type || 'compute';
            const subtype = actor.actor_subtype || actor.subtype || '';
            const status = actor.lifecycle_state || actor.status || 'active';
            const typeInfo = ACTOR_TYPE_COLORS[type] || ACTOR_TYPE_COLORS.compute;
            const TypeIcon = typeInfo.icon || Cpu;

            return (
              <div
                key={actor.id}
                onClick={() => setSelectedActor(actor)}
                className="xp-card-interactive"
                style={{
                  padding: 'var(--xp-space-4)',
                  borderLeft: `3px solid ${typeInfo.bg}`,
                }}
              >
                {/* Card header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--xp-space-3)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
                    <TypeIcon size={16} style={{ color: typeInfo.bg }} />
                    <div>
                      <div style={{ fontSize: 'var(--xp-text-base)', fontWeight: 'var(--xp-weight-semibold)', color: 'var(--xp-text-primary)' }}>
                        {actor.role || actor.alias || actor.id?.slice(0, 8)}
                      </div>
                      <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', marginTop: 2 }}>
                        {type}.{subtype}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      fontSize: 'var(--xp-text-xs)', color: STATUS_COLORS[status] || 'var(--xp-text-muted)',
                    }}>
                      <div style={{ width: 6, height: 6, borderRadius: '50%', background: STATUS_COLORS[status] || 'var(--xp-text-muted)' }} />
                      {status}
                    </div>
                    <button
                      className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm"
                      onClick={(e) => handleDelete(actor.id, e)}
                      title="Delete actor"
                      style={{ color: 'var(--xp-text-muted)' }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Alias */}
                {actor.alias && (
                  <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-secondary)', marginBottom: 'var(--xp-space-2)' }}>
                    Alias: {actor.alias}
                  </div>
                )}

                {/* ID */}
                <div style={{
                  fontSize: '10px', fontFamily: 'var(--xp-font-mono)',
                  color: 'var(--xp-text-muted)', padding: '4px 8px',
                  background: 'var(--xp-bg-elevated)', borderRadius: 'var(--xp-radius-sm)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {actor.id}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {!loading && actors.length === 0 && !error && (
        <div className="xp-empty xp-animate-fade-in">
          <div style={{ fontSize: 48, marginBottom: 12 }}>🤖</div>
          <div className="xp-empty-title">No actors registered</div>
          <div className="xp-empty-desc">Create your first actor to get started.</div>
        </div>
      )}

      {/* Detail panel */}
      {selectedActor && (
        <ActorDetail actor={selectedActor} onClose={() => setSelectedActor(null)} />
      )}

      {/* Create modal */}
      {showCreateModal && (
        <CreateActorModal onClose={() => setShowCreateModal(false)} onCreated={() => { setShowCreateModal(false); fetchActors(); }} />
      )}
    </div>
  );
}


/* ─── Actor Detail Slide-over ──────────────────────────────── */
function ActorDetail({ actor, onClose }) {
  const [edges, setEdges] = useState([]);
  const type = actor.actor_type || actor.type || 'compute';
  const typeInfo = ACTOR_TYPE_COLORS[type] || ACTOR_TYPE_COLORS.compute;

  useEffect(() => {
    actorsAPI.edges(actor.id).then(r => setEdges(r.data?.edges || [])).catch(() => {});
  }, [actor.id]);

  return (
    <>
    {/* Backdrop overlay */}
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 99 }} onClick={onClose} />
    <div style={{
      position: 'fixed', top: 0, right: 0, bottom: 0, width: 420,
      background: 'var(--xp-bg-surface)', borderLeft: '1px solid var(--xp-border-default)',
      zIndex: 100, padding: 'var(--xp-space-6)', overflowY: 'auto',
      boxShadow: 'var(--xp-shadow-xl)',
    }} className="xp-animate-slide-right">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-4)' }}>
        <h2 style={{ margin: 0, fontSize: 'var(--xp-text-lg)', fontWeight: 'var(--xp-weight-bold)', color: 'var(--xp-text-primary)' }}>
          Actor Detail
        </h2>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--xp-text-muted)', cursor: 'pointer', fontSize: 20 }}>✕</button>
      </div>

      {/* Badge */}
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '4px 12px', borderRadius: 'var(--xp-radius-full)',
        background: `${typeInfo.bg}20`, color: typeInfo.bg, fontSize: 'var(--xp-text-sm)', fontWeight: 600,
        marginBottom: 'var(--xp-space-4)',
      }}>
        {typeInfo.label}
      </div>

      {/* Fields */}
      <div style={{ display: 'grid', gap: 'var(--xp-space-3)' }}>
        {[
          ['ID', actor.id],
          ['Role', actor.role],
          ['Alias', actor.alias],
          ['Type', `${actor.actor_type}.${actor.actor_subtype}`],
          ['Status', actor.lifecycle_state || actor.status],
          ['Parent', actor.parent_id || '—'],
          ['Created', actor.created_at],
        ].map(([label, value]) => (
          <div key={label}>
            <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-primary)', fontFamily: label === 'ID' ? 'var(--xp-font-mono)' : 'inherit', wordBreak: 'break-all' }}>{value || '—'}</div>
          </div>
        ))}
      </div>

      {/* Edges */}
      {edges.length > 0 && (
        <div style={{ marginTop: 'var(--xp-space-6)' }}>
          <h3 style={{ fontSize: 'var(--xp-text-sm)', fontWeight: 600, color: 'var(--xp-text-primary)', marginBottom: 'var(--xp-space-2)' }}>
            Relationships ({edges.length})
          </h3>
          {edges.map((e, i) => (
            <div key={i} style={{
              padding: '8px 12px', background: 'var(--xp-bg-subtle)', borderRadius: 'var(--xp-radius-md)',
              marginBottom: 6, fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-secondary)',
              display: 'flex', justifyContent: 'space-between',
            }}>
              <span>{e.edge_type}</span>
              <span style={{ fontFamily: 'var(--xp-font-mono)' }}>{(e.target_id || '').slice(0, 8)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
    </>
  );
}


/* ─── Create Actor Modal ───────────────────────────────────── */
function CreateActorModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ actor_type: '', actor_subtype: '', role: '', alias: '' });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  
  const [actorTypes, setActorTypes] = useState([]);
  const [subtypes, setSubtypes] = useState([]);
  const [loadingTypes, setLoadingTypes] = useState(true);

  // Fetch actor_type and actor_subtype from the Type Registry
  useEffect(() => {
    Promise.all([
      typesAPI.list('actor_type'),
      typesAPI.list('actor_subtype')
    ]).then(([typesRes, subtypesRes]) => {
      const types = typesRes.data?.types || [];
      const subs = subtypesRes.data?.types || [];
      setActorTypes(types);
      setSubtypes(subs);
      if (types.length > 0) {
        const defaultType = types.find(t => t.name === 'ai')?.name || types[0].name;
        const matchingSubs = subs.filter(s => s.parent_name === defaultType);
        const defaultSub = matchingSubs.length > 0 ? matchingSubs[0].name : '';
        setForm(f => ({ ...f, actor_type: defaultType, actor_subtype: defaultSub }));
      }
    }).catch(err => {
      setError('Failed to load types: ' + err.message);
    }).finally(() => setLoadingTypes(false));
  }, []);

  // Update subtype when type changes
  const handleTypeChange = (newType) => {
    const matchingSubs = subtypes.filter(s => s.parent_name === newType);
    const defaultSub = matchingSubs.length > 0 ? matchingSubs[0].name : '';
    setForm(f => ({ ...f, actor_type: newType, actor_subtype: defaultSub }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.role.trim()) { setError('Role is required'); return; }
    if (!form.actor_type) { setError('Actor Type is required'); return; }
    setSubmitting(true);
    try {
      await actorsAPI.create(form);
      onCreated();
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  return (
    <ModalPortal>
      <div style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
      }} onClick={onClose}>
      <div style={{
        background: 'var(--xp-bg-surface)', borderRadius: 'var(--xp-radius-xl)',
        padding: 'var(--xp-space-6)', width: 400, maxWidth: '90vw',
        border: '1px solid var(--xp-border-default)',
      }} onClick={(e) => e.stopPropagation()} className="xp-animate-fade-in">
        <h2 style={{ margin: '0 0 var(--xp-space-4)', fontSize: 'var(--xp-text-lg)', fontWeight: 700, color: 'var(--xp-text-primary)' }}>
          Create Actor
        </h2>

        {error && <div className="xp-alert xp-alert-error" style={{ marginBottom: 12 }}>{error}</div>}

        {loadingTypes ? (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--xp-text-muted)' }}>Loading registry types...</div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 'var(--xp-space-3)' }}>
            <div>
              <label style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', display: 'block', marginBottom: 4 }}>Actor Type</label>
              <select className="xp-input" value={form.actor_type} onChange={e => handleTypeChange(e.target.value)} required>
                {actorTypes.map(t => (
                  <option key={t.name} value={t.name}>{t.display_name || t.name}</option>
                ))}
              </select>
            </div>
            
            {subtypes.filter(s => s.parent_name === form.actor_type).length > 0 && (
              <div>
                <label style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', display: 'block', marginBottom: 4 }}>Subtype</label>
                <select className="xp-input" value={form.actor_subtype} onChange={e => setForm(f => ({...f, actor_subtype: e.target.value}))} required>
                  {subtypes.filter(s => s.parent_name === form.actor_type).map(t => (
                    <option key={t.name} value={t.name}>{t.display_name || t.name}</option>
                  ))}
                </select>
              </div>
            )}

          <div>
            <label style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', display: 'block', marginBottom: 4 }}>Role</label>
            <input className="xp-input" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} placeholder="e.g., Lead Analyst" />
          </div>
          <div>
            <label style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', display: 'block', marginBottom: 4 }}>Alias</label>
            <input className="xp-input" value={form.alias} onChange={e => setForm(f => ({ ...f, alias: e.target.value }))} placeholder="Optional friendly name" />
          </div>
          <div style={{ display: 'flex', gap: 'var(--xp-space-2)', justifyContent: 'flex-end', marginTop: 'var(--xp-space-2)' }}>
            <button type="button" className="xp-btn xp-btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="xp-btn xp-btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Actor'}
            </button>
          </div>
        </form>
        )}
      </div>
      </div>
    </ModalPortal>
  );
}
