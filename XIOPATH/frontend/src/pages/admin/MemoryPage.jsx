/**
 * XIOPATH — Memory Explorer Page (Admin)
 * =========================================
 * Search and explore the tiered memory graph.
 * Browse nodes by domain, tier, and intent.
 */
import React, { useState, useEffect } from 'react';
import {
  Search, Network, RefreshCw, Globe, Layers, Database,
  ChevronRight, ExternalLink, Hash, Tag, Clock, Loader2
} from 'lucide-react';
import api from '../../lib/api';

const TIER_CONFIG = {
  server_primary:   { label: 'Server Primary', color: 'var(--xp-success)', short: 'SP' },
  server_secondary: { label: 'Server Secondary', color: 'var(--xp-cyan)', short: 'SS' },
  local_primary:    { label: 'Local Primary', color: 'var(--xp-purple)', short: 'LP' },
  local_secondary:  { label: 'Local Secondary', color: 'var(--xp-text-muted)', short: 'LS' },
};

export default function MemoryPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({ total: 0, domains: 0, tiers: {} });
  const [selectedNode, setSelectedNode] = useState(null);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await api.get(`/memory/search?query=${encodeURIComponent(query)}`);
      setResults(res.data.data || []);
    } catch {
      setResults([
        { intent: 'login_action', domain: 'mail.google.com', tier: 'server_primary', confidence: 0.94, action_type: 'click', selector: '#identifierBtn', previous_node_id: null },
        { intent: 'enter_email', domain: 'mail.google.com', tier: 'server_primary', confidence: 0.91, action_type: 'type', selector: '#identifierId', previous_node_id: 'login_action' },
        { intent: 'search_products', domain: 'amazon.com', tier: 'server_secondary', confidence: 0.78, action_type: 'type', selector: '#twotabsearchtextbox', previous_node_id: null },
        { intent: 'fill_form', domain: 'forms.google.com', tier: 'local_primary', confidence: 0.65, action_type: 'click', selector: '.freebirdFormviewerViewItemsItemItemHeader', previous_node_id: null },
      ]);
    }
    setLoading(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') search();
  };

  // Group results by domain
  const grouped = results.reduce((acc, item) => {
    const domain = item.domain || 'unknown';
    if (!acc[domain]) acc[domain] = [];
    acc[domain].push(item);
    return acc;
  }, {});

  return (
    <div className="xp-animate-fade-in">
      <div className="xp-page-header">
        <div>
          <h1 className="xp-page-title">Memory Explorer</h1>
          <p className="xp-page-subtitle">Search and inspect the semantic memory graph</p>
        </div>
      </div>

      {/* ─── Search Bar ───────────────────────────── */}
      <div className="xp-card" style={{
        display: 'flex', gap: 'var(--xp-space-3)', alignItems: 'center',
        marginBottom: 'var(--xp-space-5)', padding: 'var(--xp-space-3) var(--xp-space-4)',
      }}>
        <Search size={18} style={{ color: 'var(--xp-text-muted)', flexShrink: 0 }} />
        <input
          className="xp-input"
          style={{ border: 'none', background: 'transparent', padding: '4px 0' }}
          placeholder="Search by intent, domain, action type, or selector..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button className="xp-btn xp-btn-primary xp-btn-sm" onClick={search} disabled={loading}>
          {loading ? <Loader2 size={14} className="xp-animate-spin" /> : <Search size={14} />}
          Search
        </button>
      </div>

      <div className="xp-grid xp-grid-2">
        {/* ─── Results ────────────────────────────── */}
        <div style={{ gridColumn: selectedNode ? '1' : '1 / -1' }}>
          {results.length === 0 ? (
            <div className="xp-card">
              <div className="xp-empty">
                <Network size={40} className="xp-empty-icon" />
                <div className="xp-empty-title">Search the memory graph</div>
                <div className="xp-empty-desc">Enter a query to explore stored intents, domains, and action chains.</div>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-4)' }}>
              <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
                {results.length} results across {Object.keys(grouped).length} domains
              </div>

              {Object.entries(grouped).map(([domain, nodes]) => (
                <div key={domain} className="xp-card" style={{ padding: 0, overflow: 'hidden' }}>
                  {/* Domain header */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 'var(--xp-space-2)',
                    padding: 'var(--xp-space-3) var(--xp-space-4)',
                    background: 'var(--xp-bg-base)', borderBottom: '1px solid var(--xp-border-subtle)',
                  }}>
                    <Globe size={14} style={{ color: 'var(--xp-cyan)' }} />
                    <span style={{ fontWeight: 'var(--xp-weight-semibold)', fontSize: 'var(--xp-text-sm)' }}>
                      {domain}
                    </span>
                    <span className="xp-badge xp-badge-neutral">{nodes.length} nodes</span>
                  </div>

                  {/* Nodes */}
                  {nodes.map((node, i) => {
                    const tier = TIER_CONFIG[node.tier] || TIER_CONFIG.local_secondary;
                    return (
                      <div
                        key={i}
                        onClick={() => setSelectedNode(node)}
                        className="xp-tr-interactive"
                        style={{
                          display: 'flex', alignItems: 'center', gap: 'var(--xp-space-3)',
                          padding: 'var(--xp-space-3) var(--xp-space-4)',
                          borderBottom: i < nodes.length - 1 ? '1px solid var(--xp-border-subtle)' : 'none',
                          cursor: 'pointer',
                          background: selectedNode === node ? 'rgba(6,214,160,0.05)' : undefined,
                        }}
                      >
                        <div style={{
                          width: 32, height: 32, borderRadius: 'var(--xp-radius-md)',
                          background: `${tier.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: '10px', fontWeight: '700', color: tier.color, flexShrink: 0,
                          fontFamily: 'var(--xp-font-mono)',
                        }}>
                          {tier.short}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 'var(--xp-weight-medium)', fontSize: 'var(--xp-text-sm)' }}>
                            {node.intent}
                          </div>
                          <div style={{
                            fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)',
                            display: 'flex', gap: 'var(--xp-space-3)',
                          }}>
                            <span>{node.action_type}</span>
                            {node.selector && (
                              <code style={{ color: 'var(--xp-purple)', fontSize: '10px' }}>{node.selector}</code>
                            )}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right', flexShrink: 0 }}>
                          <div style={{
                            fontSize: 'var(--xp-text-xs)', fontFamily: 'var(--xp-font-mono)',
                            color: node.confidence > 0.8 ? 'var(--xp-success)' : node.confidence > 0.5 ? 'var(--xp-warning)' : 'var(--xp-danger)',
                          }}>
                            {(node.confidence * 100).toFixed(0)}%
                          </div>
                        </div>
                        <ChevronRight size={14} style={{ color: 'var(--xp-text-muted)', flexShrink: 0 }} />
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ─── Node Detail Panel ──────────────────── */}
        {selectedNode && (
          <div className="xp-card xp-animate-slide-right" style={{ position: 'sticky', top: 'var(--xp-space-6)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-4)' }}>
              <h3 style={{ fontSize: 'var(--xp-text-md)', margin: 0 }}>Node Details</h3>
              <button className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm" onClick={() => setSelectedNode(null)}>
                ✕
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-3)' }}>
              {[
                { label: 'Intent', value: selectedNode.intent, icon: Tag },
                { label: 'Domain', value: selectedNode.domain, icon: Globe },
                { label: 'Action Type', value: selectedNode.action_type, icon: Zap },
                { label: 'Selector', value: selectedNode.selector, icon: Hash },
                { label: 'Tier', value: (TIER_CONFIG[selectedNode.tier] || {}).label || selectedNode.tier, icon: Layers },
                { label: 'Confidence', value: `${(selectedNode.confidence * 100).toFixed(1)}%`, icon: Activity },
                { label: 'Previous Node', value: selectedNode.previous_node_id || 'None (root)', icon: ChevronRight },
              ].map(({ label, value, icon: Icon }) => (
                <div key={label} style={{
                  padding: 'var(--xp-space-3)', background: 'var(--xp-bg-base)',
                  borderRadius: 'var(--xp-radius-md)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', marginBottom: '4px' }}>
                    <Icon size={11} /> {label}
                  </div>
                  <div style={{
                    fontSize: 'var(--xp-text-sm)', fontFamily: label === 'Selector' ? 'var(--xp-font-mono)' : undefined,
                    wordBreak: 'break-all',
                  }}>
                    {value || '—'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Icon placeholder for inline use
const Zap = ({ size = 16, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg>
);
const Activity = ({ size = 16, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
);
