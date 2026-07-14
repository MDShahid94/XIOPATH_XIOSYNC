/**
 * XIOPATH — Type Registry Page (v5.0)
 * ====================================
 * Manages dynamic types (actors, edges, operations, events).
 * Allows viewing builtin types and registering/deprecating custom ones.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { typesAPI } from '../../lib/api-v2';
import useAuthStore from '../../stores/authStore';
import { ShieldCheck, Plus, Trash2, ShieldAlert, Code2, CheckCircle2, AlertCircle } from 'lucide-react';
import ModalPortal from '../../components/ModalPortal';
import useToastStore from '../../stores/toastStore';

const CATEGORY_LABELS = {
  actor_type: 'Actor Types',
  actor_subtype: 'Actor Subtypes',
  edge_type: 'Edge Types',
  operation_type: 'Operations',
  lifecycle_state: 'Lifecycle States',
  lifecycle_phase: 'Lifecycle Phases',
  event_type: 'Event Types',
  severity: 'Severities',
  capability_type: 'Capabilities',
  action_type: 'Action Types'
};

export default function TypesPage() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  
  const [categories, setCategories] = useState({});
  const [activeCategory, setActiveCategory] = useState('actor_type');
  const [types, setTypes] = useState([]);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [selectedType, setSelectedType] = useState(null);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const addToast = useToastStore((s) => s.addToast);

  const fetchOverview = useCallback(async () => {
    try {
      const res = await typesAPI.list();
      setCategories(res.data?.categories || {});
      // Set initial active category if none set and categories exist
      if (!activeCategory && res.data?.categories) {
        const cats = Object.keys(res.data.categories);
        if (cats.length > 0) setActiveCategory(cats[0]);
      }
    } catch (err) {
      console.error(err);
    }
  }, [activeCategory]);

  const fetchTypes = useCallback(async (cat) => {
    if (!cat) return;
    try {
      setLoading(true);
      const res = await typesAPI.list(cat);
      setTypes(res.data?.types || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  useEffect(() => {
    if (activeCategory) {
      fetchTypes(activeCategory);
    }
  }, [activeCategory, fetchTypes]);

  const handleAction = async (action, name) => {
    if (!window.confirm(`Are you sure you want to ${action} ${name}?`)) return;
    try {
      if (action === 'delete') {
        await typesAPI.delete(activeCategory, name);
      } else if (action === 'deprecate') {
        await typesAPI.deprecate(activeCategory, name);
      }
      fetchTypes(activeCategory);
      setSelectedType(null);
      addToast(`Successfully applied action: ${action}`, 'success');
    } catch (err) {
      addToast(err.message, 'error');
    }
  };

  return (
    <div className="xp-animate-fade-in" style={{ padding: 'var(--xp-space-6)', display: 'flex', gap: 'var(--xp-space-6)', height: '100%' }}>
      
      {/* Left Sidebar - Categories */}
      <div style={{ width: '240px', flexShrink: 0 }}>
        <h1 style={{ fontSize: 'var(--xp-text-2xl)', fontWeight: 'var(--xp-weight-bold)', color: 'var(--xp-text-primary)', fontFamily: 'var(--xp-font-display)', margin: '0 0 var(--xp-space-1)' }}>
          Type Registry
        </h1>
        <p style={{ color: 'var(--xp-text-muted)', fontSize: 'var(--xp-text-sm)', marginBottom: 'var(--xp-space-6)' }}>
          System Ontologies & Schemas
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {Object.keys(CATEGORY_LABELS).map(cat => {
            const count = categories[cat]?.length || 0;
            const isActive = activeCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 12px', borderRadius: 'var(--xp-radius-md)',
                  background: isActive ? 'var(--xp-bg-elevated)' : 'transparent',
                  border: `1px solid ${isActive ? 'var(--xp-border-strong)' : 'transparent'}`,
                  color: isActive ? 'var(--xp-cyan)' : 'var(--xp-text-secondary)',
                  cursor: 'pointer', textAlign: 'left',
                  transition: 'all 0.2s ease'
                }}
              >
                <span style={{ fontSize: 'var(--xp-text-sm)', fontWeight: isActive ? 600 : 400 }}>
                  {CATEGORY_LABELS[cat]}
                </span>
                <span style={{ 
                  background: isActive ? 'var(--xp-cyan-muted)' : 'var(--xp-bg-subtle)', 
                  color: isActive ? 'var(--xp-cyan)' : 'var(--xp-text-muted)',
                  padding: '2px 8px', borderRadius: 'var(--xp-radius-full)', 
                  fontSize: '10px', fontWeight: 700 
                }}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* Header bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-4)' }}>
          <h2 style={{ fontSize: 'var(--xp-text-xl)', color: 'var(--xp-text-primary)', fontWeight: 600, margin: 0 }}>
            {CATEGORY_LABELS[activeCategory]}
          </h2>
          {isAdmin && (
            <button className="xp-btn xp-btn-primary" onClick={() => setShowRegisterModal(true)}>
              <Plus size={16} /> Register Type
            </button>
          )}
        </div>

        {error && (
          <div style={{ padding: '12px', background: 'var(--xp-danger-bg)', color: 'var(--xp-danger)', borderRadius: 'var(--xp-radius-md)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle size={16} /> {error}
          </div>
        )}

        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--xp-space-12)' }}>
            <div className="xp-animate-spin" style={{ width: 24, height: 24, border: '2px solid var(--xp-border-subtle)', borderTop: '2px solid var(--xp-cyan)', borderRadius: '50%' }} />
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 'var(--xp-space-4)', alignContent: 'start' }}>
            {types.map(type => (
              <div
                key={type.name}
                onClick={() => setSelectedType(type)}
                className="xp-card"
                style={{
                  padding: 'var(--xp-space-4)', cursor: 'pointer',
                  border: selectedType?.name === type.name ? '1px solid var(--xp-cyan)' : '1px solid var(--xp-border-default)',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  position: 'relative', overflow: 'hidden'
                }}
                onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--xp-shadow-lg)'; }}
                onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
              >
                {type.is_builtin && (
                  <div style={{ position: 'absolute', top: 0, right: 0, padding: '4px 8px', background: 'var(--xp-bg-subtle)', borderBottomLeftRadius: 'var(--xp-radius-md)', fontSize: '10px', color: 'var(--xp-text-muted)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <ShieldCheck size={12} /> SYSTEM
                  </div>
                )}
                
                <div style={{ fontSize: 'var(--xp-text-base)', fontWeight: 600, color: 'var(--xp-text-primary)', marginBottom: '4px', paddingRight: '60px' }}>
                  {type.display_name || type.name}
                </div>
                
                <div style={{ fontSize: '11px', fontFamily: 'var(--xp-font-mono)', color: 'var(--xp-cyan)', marginBottom: '12px' }}>
                  {type.name}
                </div>
                
                <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-secondary)', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', height: '40px' }}>
                  {type.description || 'No description provided.'}
                </div>

                <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
                  {type.has_schema && (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '10px', padding: '2px 8px', background: 'var(--xp-purple-muted)', color: 'var(--xp-purple)', borderRadius: 'var(--xp-radius-full)', fontWeight: 600 }}>
                      <Code2 size={12} /> JSON SCHEMA
                    </span>
                  )}
                  {type.parent_name && (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '10px', padding: '2px 8px', background: 'var(--xp-bg-subtle)', color: 'var(--xp-text-muted)', borderRadius: 'var(--xp-radius-full)' }}>
                      Parent: {type.parent_name}
                    </span>
                  )}
                </div>
              </div>
            ))}
            
            {types.length === 0 && (
              <div style={{ gridColumn: '1 / -1', padding: 'var(--xp-space-12)', textAlign: 'center', color: 'var(--xp-text-muted)' }}>
                No types registered in this category.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right Sidebar - Detail Panel */}
      {selectedType && (
        <TypeDetail 
          category={activeCategory} 
          typeName={selectedType.name} 
          onClose={() => setSelectedType(null)} 
          isAdmin={isAdmin}
          onAction={handleAction}
        />
      )}

      {/* Register Modal */}
      {showRegisterModal && (
        <RegisterTypeModal 
          defaultCategory={activeCategory}
          onClose={() => setShowRegisterModal(false)}
          onSuccess={() => { setShowRegisterModal(false); fetchTypes(activeCategory); fetchOverview(); }}
        />
      )}
    </div>
  );
}

function TypeDetail({ category, typeName, onClose, isAdmin, onAction }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    typesAPI.get(category, typeName).then(res => {
      setDetail(res.data);
    }).catch(err => console.error(err)).finally(() => setLoading(false));
  }, [category, typeName]);

  return (
    <div className="xp-animate-fade-in" style={{
      width: '380px', flexShrink: 0, background: 'var(--xp-bg-surface)', 
      borderLeft: '1px solid var(--xp-border-default)', padding: 'var(--xp-space-6)',
      overflowY: 'auto', display: 'flex', flexDirection: 'column'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-6)' }}>
        <h3 style={{ margin: 0, fontSize: 'var(--xp-text-lg)', color: 'var(--xp-text-primary)' }}>Type Details</h3>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--xp-text-muted)', cursor: 'pointer' }}>✕</button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', color: 'var(--xp-text-muted)', marginTop: '40px' }}>Loading...</div>
      ) : detail ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-4)' }}>
          <div>
            <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>Name (ID)</div>
            <div style={{ fontSize: 'var(--xp-text-sm)', fontFamily: 'var(--xp-font-mono)', color: 'var(--xp-cyan)', marginTop: '4px' }}>{detail.name}</div>
          </div>
          
          <div>
            <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>Display Name</div>
            <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-primary)', marginTop: '4px' }}>{detail.display_name || '—'}</div>
          </div>

          <div>
            <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>Description</div>
            <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-secondary)', marginTop: '4px', lineHeight: 1.5 }}>{detail.description || '—'}</div>
          </div>
          
          <div style={{ display: 'flex', gap: '12px' }}>
            <div>
              <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>Type</div>
              <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-primary)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {detail.is_builtin ? <><ShieldCheck size={14} color="var(--xp-cyan)" /> Built-in</> : 'Custom'}
              </div>
            </div>
            {detail.parent_name && (
              <div>
                <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>Parent</div>
                <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-primary)', marginTop: '4px' }}>{detail.parent_name}</div>
              </div>
            )}
          </div>

          {detail.schema && (
            <div style={{ marginTop: '8px' }}>
              <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Code2 size={14} /> JSON Schema
              </div>
              <div style={{ 
                background: 'var(--xp-bg-void)', padding: '12px', borderRadius: 'var(--xp-radius-md)',
                fontFamily: 'var(--xp-font-mono)', fontSize: '11px', color: 'var(--xp-text-secondary)',
                overflowX: 'auto', border: '1px solid var(--xp-border-subtle)'
              }}>
                <pre style={{ margin: 0 }}>{JSON.stringify(detail.schema, null, 2)}</pre>
              </div>
            </div>
          )}

          {/* Admin Controls */}
          {isAdmin && !detail.is_builtin && (
            <div style={{ marginTop: 'auto', paddingTop: 'var(--xp-space-6)', borderTop: '1px solid var(--xp-border-default)', display: 'flex', gap: '8px' }}>
              {detail.state !== 'deprecated' && (
                <button onClick={() => onAction('deprecate', detail.name)} className="xp-btn xp-btn-ghost" style={{ flex: 1, color: 'var(--xp-warning)' }}>
                  <ShieldAlert size={14} /> Deprecate
                </button>
              )}
              <button onClick={() => onAction('delete', detail.name)} className="xp-btn xp-btn-ghost" style={{ flex: 1, color: 'var(--xp-danger)' }}>
                <Trash2 size={14} /> Delete
              </button>
            </div>
          )}
        </div>
      ) : (
        <div style={{ color: 'var(--xp-danger)' }}>Failed to load details.</div>
      )}
    </div>
  );
}

function RegisterTypeModal({ defaultCategory, onClose, onSuccess }) {
  const [form, setForm] = useState({
    category: defaultCategory || 'actor_type',
    name: '',
    display_name: '',
    description: '',
    parent_name: '',
    schema: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const payload = { ...form };
      if (!payload.name) throw new Error("Name is required");
      
      if (payload.schema) {
        try {
          payload.schema = JSON.parse(payload.schema);
        } catch(err) {
          throw new Error("Invalid JSON Schema format");
        }
      } else {
        delete payload.schema;
      }
      
      if (!payload.parent_name) delete payload.parent_name;
      
      await typesAPI.register(payload);
      onSuccess();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalPortal>
      <div style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 999,
        display: 'flex', alignItems: 'center', justifyContent: 'center'
      }}>
      <div className="xp-animate-fade-in" style={{
        background: 'var(--xp-bg-surface)', padding: 'var(--xp-space-6)',
        borderRadius: 'var(--xp-radius-xl)', width: '500px', maxWidth: '90vw',
        border: '1px solid var(--xp-border-strong)', boxShadow: 'var(--xp-shadow-2xl)'
      }}>
        <h2 style={{ margin: '0 0 var(--xp-space-4)', color: 'var(--xp-text-primary)' }}>Register Custom Type</h2>
        
        {error && <div style={{ color: 'var(--xp-danger)', background: 'var(--xp-danger-bg)', padding: '8px', borderRadius: '4px', marginBottom: '16px', fontSize: '12px' }}>{error}</div>}
        
        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 'var(--xp-space-3)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--xp-text-muted)', marginBottom: '4px' }}>Category</label>
              <select className="xp-input" value={form.category} onChange={e => setForm({...form, category: e.target.value})}>
                {Object.entries(CATEGORY_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--xp-text-muted)', marginBottom: '4px' }}>Parent Type (optional)</label>
              <input className="xp-input" placeholder="e.g. human" value={form.parent_name} onChange={e => setForm({...form, parent_name: e.target.value})} />
            </div>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--xp-text-muted)', marginBottom: '4px' }}>Name (ID)</label>
              <input className="xp-input" placeholder="my_custom_type" value={form.name} onChange={e => setForm({...form, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g,'')})} required />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--xp-text-muted)', marginBottom: '4px' }}>Display Name</label>
              <input className="xp-input" placeholder="My Custom Type" value={form.display_name} onChange={e => setForm({...form, display_name: e.target.value})} />
            </div>
          </div>
          
          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--xp-text-muted)', marginBottom: '4px' }}>Description</label>
            <textarea className="xp-input" rows={2} value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
          </div>
          
          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--xp-text-muted)', marginBottom: '4px' }}>JSON Schema (optional)</label>
            <textarea className="xp-input" rows={4} placeholder="{ &quot;type&quot;: &quot;object&quot;, ... }" style={{ fontFamily: 'var(--xp-font-mono)', fontSize: '11px' }} value={form.schema} onChange={e => setForm({...form, schema: e.target.value})} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '12px' }}>
            <button type="button" onClick={onClose} className="xp-btn xp-btn-ghost">Cancel</button>
            <button type="submit" disabled={loading} className="xp-btn xp-btn-primary">{loading ? 'Saving...' : 'Register Type'}</button>
          </div>
        </form>
      </div>
      </div>
    </ModalPortal>
  );
}
