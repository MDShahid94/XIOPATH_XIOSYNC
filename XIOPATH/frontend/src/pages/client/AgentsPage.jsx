/**
 * XIOPATH — Agents & Environments Page (Phase F.4)
 * ===================================================
 * Manage agents and installed workflow environments.
 * Two-tab layout: Agents grid + Environments list.
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Bot, Package, Cpu, Play, Trash2, Settings2, RefreshCw,
  ChevronRight, Shield, Zap, Clock, Globe, Box, Eye,
  AlertTriangle, CheckCircle, Archive,
} from 'lucide-react';
import useAgentStore from '../../stores/agentStore';

const AGENT_TYPE_ICONS = {
  'compute.work_runtime': Cpu,
  'compute.sub_runtime': Zap,
  'io.browser_driver': Globe,
  'io.network_proxy': Shield,
  'meta.supervisor': Eye,
  'meta.orchestrator': Settings2,
};

const STATE_COLORS = {
  active: 'var(--xp-success)',
  idle: 'var(--xp-text-muted)',
  running: 'var(--xp-cyan)',
  error: 'var(--xp-error)',
  archived: 'var(--xp-text-disabled)',
};

function AgentCard({ agent }) {
  const agentType = agent.agent_type || agent.type || 'compute.work_runtime';
  const Icon = AGENT_TYPE_ICONS[agentType] || Bot;
  const state = agent.state || agent.status || 'idle';
  const stateColor = STATE_COLORS[state] || STATE_COLORS.idle;

  return (
    <div className="xp-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-3)' }}>
        <div style={{ color: 'var(--xp-text-primary)' }}>
          <Icon size={20} />
        </div>
        <span className="xp-badge" style={{ background: `${stateColor}20`, color: stateColor, borderColor: `${stateColor}40` }}>
          {state}
        </span>
      </div>
      <h3 style={{ margin: '0 0 4px 0', fontSize: 'var(--xp-text-base)', fontWeight: 'var(--xp-weight-semibold)' }}>{agent.name || agent.id?.slice(0, 12)}</h3>
      <p style={{ margin: 0, fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>{agentType}</p>
      <div style={{ display: 'flex', gap: 'var(--xp-space-3)', marginTop: 'var(--xp-space-4)', fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-secondary)' }}>
        {agent.created_at && (
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Clock size={11} /> {new Date(agent.created_at).toLocaleDateString()}
          </span>
        )}
        {agent.version && (
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Box size={11} /> v{agent.version}
          </span>
        )}
      </div>
    </div>
  );
}

function EnvironmentRow({ env, onDelete }) {
  const state = env.state || 'active';
  const stateColor = STATE_COLORS[state] || STATE_COLORS.active;
  const envType = env.environment_type || 'workflow_bundle';

  return (
    <div className="xp-card" style={{ display: 'flex', alignItems: 'center', padding: 'var(--xp-space-4)', marginBottom: 'var(--xp-space-2)' }}>
      <div style={{ width: 32, height: 32, borderRadius: 'var(--xp-radius-md)', background: 'var(--xp-bg-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: 'var(--xp-space-4)', color: 'var(--xp-cyan)' }}>
        <Package size={18} />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 'var(--xp-weight-medium)', fontSize: 'var(--xp-text-sm)', marginBottom: '4px' }}>{env.id?.slice(0, 16)}...</div>
        <div style={{ display: 'flex', gap: 'var(--xp-space-2)', fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
          <span>{envType}</span>
          <span>•</span>
          <span style={{ color: stateColor }}>{state}</span>
          {env.visibility && (
            <>
              <span>•</span>
              <span>{env.visibility}</span>
            </>
          )}
        </div>
      </div>
      <div>
        <button className="xp-btn xp-btn-ghost xp-btn-icon" title="Archive" onClick={() => onDelete(env.id)} style={{ color: 'var(--xp-text-muted)' }}>
          <Archive size={14} />
        </button>
      </div>
    </div>
  );
}

export default function AgentsPage() {
  const {
    agents, environments, loading, error,
    fetchAgents, fetchEnvironments, deleteEnvironment, clearError,
  } = useAgentStore();

  const [tab, setTab] = useState('agents');

  useEffect(() => {
    fetchAgents();
    fetchEnvironments();
  }, [fetchAgents, fetchEnvironments]);

  const handleRefresh = useCallback(() => {
    if (tab === 'agents') fetchAgents();
    else fetchEnvironments();
  }, [tab, fetchAgents, fetchEnvironments]);

  return (
    <div className="xp-animate-fade-in" style={{ padding: 'var(--xp-space-6)' }}>
      {/* Header */}
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title" style={{ display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)' }}>
            <Bot size={28} style={{ color: 'var(--xp-cyan)' }} /> Agents & Environments
          </h1>
          <p className="xp-page-subtitle">Manage your agents and installed workflow environments</p>
        </div>
        <button className="xp-btn xp-btn-secondary" onClick={handleRefresh}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 'var(--xp-space-4)', borderBottom: '1px solid var(--xp-border-subtle)', marginBottom: 'var(--xp-space-6)' }}>
        <button
          style={{
            background: 'none', border: 'none', padding: 'var(--xp-space-3) 0',
            color: tab === 'agents' ? 'var(--xp-cyan)' : 'var(--xp-text-muted)',
            borderBottom: tab === 'agents' ? '2px solid var(--xp-cyan)' : '2px solid transparent',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)',
            fontWeight: tab === 'agents' ? 600 : 400,
          }}
          onClick={() => setTab('agents')}
        >
          <Bot size={15} /> Agents
          <span className="xp-badge xp-badge-neutral">{agents.length}</span>
        </button>
        <button
          style={{
            background: 'none', border: 'none', padding: 'var(--xp-space-3) 0',
            color: tab === 'environments' ? 'var(--xp-cyan)' : 'var(--xp-text-muted)',
            borderBottom: tab === 'environments' ? '2px solid var(--xp-cyan)' : '2px solid transparent',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)',
            fontWeight: tab === 'environments' ? 600 : 400,
          }}
          onClick={() => setTab('environments')}
        >
          <Package size={15} /> Environments
          <span className="xp-badge xp-badge-neutral">{environments.length}</span>
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="xp-alert xp-alert-error" style={{ margin: '0 0 16px' }}>
          <AlertTriangle size={14} /> {error}
          <button onClick={clearError} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>×</button>
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 'var(--xp-space-12)', color: 'var(--xp-text-muted)' }}>
          <div className="xp-animate-spin" style={{
            width: 28, height: 28, border: '2px solid var(--xp-border-subtle)',
            borderTop: '2px solid var(--xp-cyan)', borderRadius: '50%',
            marginBottom: 'var(--xp-space-3)'
          }} />
          <span>Loading...</span>
        </div>
      ) : tab === 'agents' ? (
        /* Agents Grid */
        agents.length === 0 ? (
          <div className="xp-empty">
            <Bot size={48} className="xp-empty-icon" />
            <div className="xp-empty-title">No agents registered</div>
            <div className="xp-empty-desc">Agents will appear here once the ontology is seeded and agents are created.</div>
          </div>
        ) : (
          <div className="xp-grid xp-grid-3">
            {agents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )
      ) : (
        /* Environments List */
        environments.length === 0 ? (
          <div className="xp-empty">
            <Package size={48} className="xp-empty-icon" />
            <div className="xp-empty-title">No environments installed</div>
            <div className="xp-empty-desc">Browse the Marketplace to install workflow environments.</div>
          </div>
        ) : (
          <div className="xp-stagger">
            {environments.map((env) => (
              <EnvironmentRow key={env.id} env={env} onDelete={deleteEnvironment} />
            ))}
          </div>
        )
      )}
    </div>
  );
}
