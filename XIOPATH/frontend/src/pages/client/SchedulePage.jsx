/**
 * XIOPATH — Schedule Center Page
 * =================================
 * Create and manage scheduled/recurring workflow executions.
 * Visual cron builder with job list and toggle controls.
 */
import React, { useState, useEffect } from 'react';
import {
  Calendar, Plus, Trash2, Play, Pause, Clock, RefreshCw,
  Loader2, X, Save, CheckCircle, AlertTriangle, Zap, Globe
} from 'lucide-react';
import api from '../../lib/api';
import ModalPortal from '../../components/ModalPortal';
import useToastStore from '../../stores/toastStore';

const CRON_PRESETS = [
  { label: 'Every 5 minutes', cron: '*/5 * * * *' },
  { label: 'Every 15 minutes', cron: '*/15 * * * *' },
  { label: 'Every hour', cron: '0 * * * *' },
  { label: 'Every 6 hours', cron: '0 */6 * * *' },
  { label: 'Daily at midnight', cron: '0 0 * * *' },
  { label: 'Daily at 9 AM', cron: '0 9 * * *' },
  { label: 'Weekly (Sunday)', cron: '0 0 * * 0' },
  { label: 'Monthly (1st)', cron: '0 0 1 * *' },
];

export default function SchedulePage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const addToast = useToastStore((s) => s.addToast);

  // Form state
  const [formName, setFormName] = useState('');
  const [formUrl, setFormUrl] = useState('');
  const [formIntent, setFormIntent] = useState('');
  const [formCron, setFormCron] = useState('0 * * * *');
  const [formEnabled, setFormEnabled] = useState(true);
  const [formLoading, setFormLoading] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => { fetchJobs(); }, []);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const res = await api.get('/schedule/jobs');
      setJobs(res.data.jobs || []);
    } catch {
      setJobs([]);
    }
    setLoading(false);
  };



  const handleCreate = async () => {
    if (!formName || !formUrl || !formIntent) {
      setFormError('Name, URL, and Intent are required.'); return;
    }
    setFormLoading(true);
    setFormError('');

    const newJob = {
      name: formName, url: formUrl, intent: formIntent,
      cron: formCron, enabled: formEnabled,
    };

    try {
      await api.post('/schedule/jobs', newJob);
      addToast('Scheduled job created', 'success');
      fetchJobs();
      setShowModal(false);
      resetForm();
    } catch (e) {
      setFormError('Failed to create job.');
    } finally {
      setFormLoading(false);
    }
  };

  const toggleJob = async (id) => {
    try {
      await api.put(`/schedule/jobs/${id}/toggle`);
      fetchJobs();
    } catch (e) {
      addToast('Failed to toggle job', 'error');
    }
  };

  const deleteJob = async (id) => {
    try {
      await api.delete(`/schedule/jobs/${id}`);
      addToast('Job deleted', 'success');
      fetchJobs();
    } catch (e) {
      addToast('Failed to delete job', 'error');
    }
  };

  const resetForm = () => {
    setFormName(''); setFormUrl(''); setFormIntent('');
    setFormCron('0 * * * *'); setFormEnabled(true); setFormError('');
  };

  const describeCron = (cron) => {
    const preset = CRON_PRESETS.find((p) => p.cron === cron);
    return preset ? preset.label : cron;
  };

  const formatTime = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  };

  return (
    <div className="xp-animate-fade-in">
      {/* ─── Header ───────────────────────────────── */}
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Schedule Center</h1>
          <p className="xp-page-subtitle">Automate recurring workflow executions</p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--xp-space-2)' }}>
          <button className="xp-btn xp-btn-secondary" onClick={fetchJobs} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'xp-animate-spin' : ''} />
          </button>
          <button className="xp-btn xp-btn-primary" onClick={() => { setShowModal(true); resetForm(); }}>
            <Plus size={14} /> New Schedule
          </button>
        </div>
      </div>

      {/* ─── Stats ────────────────────────────────── */}
      <div className="xp-grid xp-grid-3" style={{ marginBottom: 'var(--xp-space-5)' }}>
        {[
          { label: 'Total Jobs', value: jobs.length, icon: Calendar, color: 'var(--xp-cyan)' },
          { label: 'Active', value: jobs.filter(j => j.enabled).length, icon: Play, color: 'var(--xp-success)' },
          { label: 'Total Runs', value: jobs.reduce((sum, j) => sum + (j.run_count || 0), 0), icon: Zap, color: 'var(--xp-purple)' },
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

      {/* ─── Jobs List ────────────────────────────── */}
      {loading ? (
        <div className="xp-card xp-stagger">
          {[1, 2, 3].map((i) => (
            <div key={i} className="xp-skeleton" style={{ height: '72px', marginBottom: 'var(--xp-space-3)' }} />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <div className="xp-card">
          <div className="xp-empty">
            <Calendar size={40} className="xp-empty-icon" />
            <div className="xp-empty-title">No scheduled jobs</div>
            <div className="xp-empty-desc">Create your first scheduled workflow to automate recurring tasks.</div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }} className="xp-stagger">
          {jobs.map((job) => (
            <div key={job.id} className="xp-card" style={{
              display: 'flex', alignItems: 'center', gap: 'var(--xp-space-4)',
              opacity: job.enabled ? 1 : 0.6,
              borderColor: job.enabled ? 'var(--xp-border-subtle)' : 'var(--xp-border-subtle)',
            }}>
              {/* Toggle */}
              <button
                onClick={() => toggleJob(job.id)}
                style={{
                  width: 44, height: 24, borderRadius: 'var(--xp-radius-full)', border: 'none',
                  background: job.enabled ? 'var(--xp-cyan)' : 'var(--xp-bg-base)',
                  cursor: 'pointer', position: 'relative', flexShrink: 0,
                  transition: 'background 200ms ease',
                  outline: '1px solid var(--xp-border-default)',
                }}
              >
                <div style={{
                  width: 18, height: 18, borderRadius: '50%', background: 'white',
                  position: 'absolute', top: '3px',
                  left: job.enabled ? '23px' : '3px',
                  transition: 'left 200ms ease',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                }} />
              </button>

              {/* Job info */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)', marginBottom: '4px' }}>
                  <span style={{ fontWeight: 'var(--xp-weight-medium)', fontSize: 'var(--xp-text-sm)' }}>
                    {job.name}
                  </span>
                  <span className={`xp-badge ${job.enabled ? 'xp-badge-success' : 'xp-badge-neutral'}`}>
                    {job.enabled ? 'Active' : 'Paused'}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-4)', fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Globe size={11} /> {job.url?.replace('https://', '')}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={11} /> {describeCron(job.cron)}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Zap size={11} /> {job.run_count} runs
                  </span>
                </div>
              </div>

              {/* Timing */}
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                  Last: {formatTime(job.last_run)}
                </div>
                <div style={{ fontSize: 'var(--xp-text-xs)', color: job.enabled ? 'var(--xp-cyan)' : 'var(--xp-text-muted)' }}>
                  Next: {job.enabled ? formatTime(job.next_run) : '—'}
                </div>
              </div>

              {/* Delete */}
              <button className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm"
                onClick={() => deleteJob(job.id)}
                style={{ color: 'var(--xp-danger)' }}
                data-tooltip="Delete"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ─── Create Modal ─────────────────────────── */}
      {showModal && (
        <ModalPortal>
          <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--xp-space-4)' }}>
            <div onClick={() => setShowModal(false)}
              style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
              className="xp-animate-fade-in"
            />
            <div style={{
              position: 'relative',
              background: 'var(--xp-bg-elevated)', border: '1px solid var(--xp-border-default)',
              borderRadius: 'var(--xp-radius-xl)', padding: 'var(--xp-space-6)',
              width: '100%', maxWidth: '480px', boxShadow: 'var(--xp-shadow-xl)',
            }} className="xp-animate-scale-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-5)' }}>
              <h3 style={{ margin: 0 }}>New Scheduled Job</h3>
              <button className="xp-btn xp-btn-ghost xp-btn-icon" onClick={() => setShowModal(false)}><X size={18} /></button>
            </div>

            {formError && (
              <div style={{
                padding: 'var(--xp-space-3)', background: 'var(--xp-danger-bg)',
                border: '1px solid rgba(239,68,68,0.2)', borderRadius: 'var(--xp-radius-md)',
                marginBottom: 'var(--xp-space-4)', fontSize: 'var(--xp-text-sm)', color: 'var(--xp-danger)',
              }}>{formError}</div>
            )}

            <div className="xp-field" style={{ marginBottom: 'var(--xp-space-4)' }}>
              <label className="xp-label">Job Name</label>
              <input className="xp-input" placeholder="e.g. Daily Login Check"
                value={formName} onChange={(e) => setFormName(e.target.value)} />
            </div>
            <div className="xp-field" style={{ marginBottom: 'var(--xp-space-4)' }}>
              <label className="xp-label">Target URL</label>
              <input className="xp-input" placeholder="https://example.com"
                value={formUrl} onChange={(e) => setFormUrl(e.target.value)} />
            </div>
            <div className="xp-field" style={{ marginBottom: 'var(--xp-space-4)' }}>
              <label className="xp-label">Start Intent</label>
              <input className="xp-input" placeholder="e.g. login_action"
                value={formIntent} onChange={(e) => setFormIntent(e.target.value)} />
            </div>
            <div className="xp-field" style={{ marginBottom: 'var(--xp-space-4)' }}>
              <label className="xp-label">Schedule (Cron)</label>
              <select className="xp-select" value={formCron}
                onChange={(e) => setFormCron(e.target.value)}>
                {CRON_PRESETS.map((p) => (
                  <option key={p.cron} value={p.cron}>{p.label} — {p.cron}</option>
                ))}
              </select>
            </div>
            <div style={{
              padding: 'var(--xp-space-3)', background: 'var(--xp-bg-base)',
              borderRadius: 'var(--xp-radius-md)', marginBottom: 'var(--xp-space-5)',
              fontSize: 'var(--xp-text-xs)', fontFamily: 'var(--xp-font-mono)',
              color: 'var(--xp-text-secondary)', textAlign: 'center',
            }}>
              Cron: <strong style={{ color: 'var(--xp-cyan)' }}>{formCron}</strong>
              <span style={{ margin: '0 8px', color: 'var(--xp-text-muted)' }}>→</span>
              {describeCron(formCron)}
            </div>

            <div style={{ display: 'flex', gap: 'var(--xp-space-3)', justifyContent: 'flex-end' }}>
              <button className="xp-btn xp-btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
              <button className="xp-btn xp-btn-primary" disabled={formLoading} onClick={handleCreate}>
                {formLoading ? <Loader2 size={14} className="xp-animate-spin" /> : <Save size={14} />}
                Create Job
              </button>
            </div>
          </div>
          </div>
        </ModalPortal>
      )}
    </div>
  );
}
