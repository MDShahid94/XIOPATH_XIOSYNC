/**
 * XIOPATH — Knowledge Explorer (v5.0)
 * ====================================
 * Semantic graph viewer for the Universal Memory manager.
 * Search, explore, and visualize learned workflows and actions.
 */
import React, { useState, useCallback } from 'react';
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState, Handle, Position
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Search, BrainCircuit, ShieldCheck, ChevronRight,
  Database, Network, Zap, GitCommit, Layers, Globe, X, Code2
} from 'lucide-react';
import { memoryAPI } from '../../lib/api-v2';

// ─── Custom Semantic Node ─────────────────────────────────
function SemanticNode({ data, selected }) {
  const isRoot = data.isRoot;
  return (
    <div style={{
      background: selected ? 'var(--xp-bg-elevated)' : 'var(--xp-bg-surface)',
      border: `1px solid ${selected ? 'var(--xp-cyan)' : isRoot ? 'var(--xp-purple)' : 'var(--xp-border-strong)'}`,
      borderRadius: 'var(--xp-radius-lg)',
      padding: '12px 16px',
      minWidth: '200px',
      boxShadow: selected ? 'var(--xp-shadow-glow-cyan)' : 'var(--xp-shadow-sm)',
      transition: 'all 200ms ease',
      opacity: data.dimmed ? 0.4 : 1,
    }}>
      <Handle type="target" position={Position.Top} style={{ opacity: isRoot ? 0 : 1, background: 'var(--xp-purple)' }} />
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <div style={{
          width: 24, height: 24, borderRadius: 'var(--xp-radius-md)',
          background: isRoot ? 'var(--xp-purple-muted)' : 'var(--xp-bg-subtle)',
          color: isRoot ? 'var(--xp-purple)' : 'var(--xp-text-primary)',
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          {isRoot ? <BrainCircuit size={14} /> : <GitCommit size={14} />}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '13px', fontWeight: '600', color: 'var(--xp-text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {data.action_type || data.intent}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--xp-text-muted)', fontFamily: 'var(--xp-font-mono)' }}>
            Tier: {data.tier || 'unknown'}
          </div>
        </div>
      </div>
      
      <div style={{ fontSize: '11px', color: 'var(--xp-text-secondary)', marginBottom: '8px', wordBreak: 'break-all' }}>
        {data.face_value || data.url || 'No face value'}
      </div>

      <div style={{ display: 'flex', gap: '4px' }}>
        <span style={{ fontSize: '9px', padding: '2px 6px', background: 'var(--xp-bg-void)', border: '1px solid var(--xp-border-subtle)', borderRadius: '4px', color: 'var(--xp-text-muted)' }}>
          {data.id ? data.id.slice(0,6) : 'root'}
        </span>
      </div>
      
      <Handle type="source" position={Position.Bottom} style={{ background: 'var(--xp-cyan)' }} />
    </div>
  );
}

const nodeTypes = { semantic: SemanticNode };

export default function KnowledgePage() {
  const [query, setQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  
  const [activeIntent, setActiveIntent] = useState(null);
  const [activeUrl, setActiveUrl] = useState(null);
  const [isLoadingGraph, setIsLoadingGraph] = useState(false);
  const [error, setError] = useState(null);
  const [selectedNodeData, setSelectedNodeData] = useState(null);
  
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Initial load
  useEffect(() => {
    // Perform an initial blank search to populate the knowledge graph list
    const doInitialSearch = async () => {
      setIsSearching(true);
      try {
        const res = await memoryAPI.search('');
        const results = res.data?.data || res.data?.results || [];
        setSearchResults(Array.isArray(results) ? results : []);
        if (Array.isArray(results) && results.length > 0) {
          loadGraph(results[0].intent, results[0].url || 'unknown');
        }
      } catch (err) {
        console.error("Initial load failed:", err);
      } finally {
        setIsSearching(false);
      }
    };
    doInitialSearch();
  }, []);

  const handleSearch = async (e) => {
    e?.preventDefault();
    if (!query.trim() && e) return;
    
    setIsSearching(true);
    setError(null);
    try {
      const res = await memoryAPI.search(query);
      // Assume backend returns array of { intent, url, similarity, tier, ... }
      // Or fallback array if none
      const results = res.data?.data || res.data?.results || [];
      setSearchResults(Array.isArray(results) ? results : []);
      
      // Auto-load first result if any
      if (Array.isArray(results) && results.length > 0) {
        loadGraph(results[0].intent, results[0].url || 'unknown');
      } else {
        setNodes([]);
        setEdges([]);
        setActiveIntent(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSearching(false);
    }
  };

  const loadGraph = async (intent, url) => {
    setIsLoadingGraph(true);
    setActiveIntent(intent);
    setActiveUrl(url);
    setError(null);
    setSelectedNodeData(null);
    try {
      const res = await memoryAPI.graph(url, intent);
      const graphData = res.data;
      
      // Transform backend graph data into ReactFlow format
      const rfNodes = [];
      const rfEdges = [];
      
      if (graphData && graphData.nodes) {
        // Layout algorithm (simple vertical tree)
        const xOffset = 300;
        let yOffset = 50;
        
        // Root node
        rfNodes.push({
          id: 'root',
          type: 'semantic',
          position: { x: xOffset, y: yOffset },
          data: { isRoot: true, intent, url, tier: 'Root' }
        });
        
        yOffset += 150;
        
        // Actions
        graphData.nodes.forEach((node, idx) => {
          rfNodes.push({
            id: node.id,
            type: 'semantic',
            position: { x: xOffset, y: yOffset + (idx * 150) },
            data: { ...node, isRoot: false }
          });
          
          if (idx === 0) {
            rfEdges.push({ id: `e-root-${node.id}`, source: 'root', target: node.id, style: { stroke: 'var(--xp-purple)', strokeWidth: 2 } });
          } else {
            rfEdges.push({ id: `e-${graphData.nodes[idx-1].id}-${node.id}`, source: graphData.nodes[idx-1].id, target: node.id, animated: true, style: { stroke: 'var(--xp-cyan)', strokeWidth: 2 } });
          }
        });
      }
      
      setNodes(rfNodes);
      setEdges(rfEdges);
    } catch (err) {
      if (err.response?.status === 404) {
         setError("No execution graph found for this intent.");
      } else {
         setError("Failed to load graph: " + err.message);
      }
      setNodes([]);
      setEdges([]);
    } finally {
      setIsLoadingGraph(false);
    }
  };

  const onNodeClick = useCallback((event, node) => {
    setSelectedNodeData(node.data);
  }, []);

  return (
    <div className="xp-animate-fade-in" style={{ display: 'flex', height: '100%', width: '100%' }}>
      
      {/* ─── Left Sidebar: Search & Results ───────────────────────── */}
      <div style={{
        width: '320px', flexShrink: 0, borderRight: '1px solid var(--xp-border-default)',
        background: 'var(--xp-bg-surface)', display: 'flex', flexDirection: 'column'
      }}>
        <div style={{ padding: 'var(--xp-space-4)', borderBottom: '1px solid var(--xp-border-subtle)' }}>
          <h2 style={{ margin: '0 0 var(--xp-space-1)', fontSize: 'var(--xp-text-xl)', color: 'var(--xp-text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BrainCircuit size={20} color="var(--xp-purple)" /> Knowledge
          </h2>
          <p style={{ margin: '0 0 var(--xp-space-4)', fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)' }}>
            Search the Universal Memory Graph
          </p>
          
          <form onSubmit={handleSearch} style={{ position: 'relative' }}>
            <input 
              type="text" 
              className="xp-input"
              style={{ paddingLeft: '32px' }}
              placeholder="e.g. login to github..."
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
            <Search size={16} color="var(--xp-text-muted)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
          </form>
        </div>
        
        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--xp-space-3)' }}>
          {isSearching ? (
             <div style={{ textAlign: 'center', padding: '20px', color: 'var(--xp-text-muted)' }}>Searching...</div>
          ) : searchResults.length > 0 ? (
            <div style={{ display: 'grid', gap: '8px' }}>
              {searchResults.map((res, i) => {
                const isActive = activeIntent === res.intent && activeUrl === res.url;
                return (
                  <div 
                    key={i}
                    onClick={() => loadGraph(res.intent, res.url)}
                    style={{
                      padding: '12px', borderRadius: 'var(--xp-radius-md)', cursor: 'pointer',
                      background: isActive ? 'var(--xp-bg-elevated)' : 'var(--xp-bg-base)',
                      border: `1px solid ${isActive ? 'var(--xp-purple)' : 'var(--xp-border-subtle)'}`,
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ fontSize: 'var(--xp-text-sm)', color: isActive ? 'var(--xp-purple)' : 'var(--xp-text-primary)', fontWeight: 600, marginBottom: '4px' }}>
                      {res.intent || 'Unknown Intent'}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--xp-text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Globe size={10} /> {res.url || 'global'}
                    </div>
                    {res.tier && (
                      <div style={{ marginTop: '8px', display: 'inline-block', fontSize: '9px', padding: '2px 6px', background: 'var(--xp-purple-muted)', color: 'var(--xp-purple)', borderRadius: '4px', fontWeight: 700, textTransform: 'uppercase' }}>
                        {res.tier} Tier
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--xp-text-muted)' }}>
              <Database size={32} style={{ opacity: 0.2, margin: '0 auto 12px' }} />
              <div style={{ fontSize: 'var(--xp-text-sm)' }}>No results found.</div>
            </div>
          )}
        </div>
      </div>

      {/* ─── Main Canvas Area ───────────────────────────────────── */}
      <div style={{ flex: 1, position: 'relative', background: 'var(--xp-bg-void)', display: 'flex' }}>
        {error && (
          <div style={{ position: 'absolute', top: 20, left: '50%', transform: 'translateX(-50%)', zIndex: 10, background: 'var(--xp-danger-bg)', color: 'var(--xp-danger)', padding: '8px 16px', borderRadius: 'var(--xp-radius-md)', border: '1px solid var(--xp-danger)', display: 'flex', alignItems: 'center', gap: '8px', boxShadow: 'var(--xp-shadow-lg)' }}>
            <Zap size={16} /> {error}
            <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', display: 'flex' }}><X size={14} /></button>
          </div>
        )}
        
        {!activeIntent ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--xp-text-muted)', flexDirection: 'column', gap: '16px' }}>
            <Layers size={64} style={{ opacity: 0.1 }} />
            <div style={{ fontSize: 'var(--xp-text-xl)', fontWeight: 300 }}>Search the semantic knowledge base</div>
          </div>
        ) : isLoadingGraph ? (
           <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--xp-purple)' }}>
             Loading execution graph...
           </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            fitView
            style={{ background: 'var(--xp-bg-void)' }}
          >
            <Background color="var(--xp-border-strong)" gap={24} size={2} />
            <Controls style={{ background: 'var(--xp-bg-surface)', border: '1px solid var(--xp-border-default)' }} />
            <MiniMap 
              nodeColor={(n) => n.data.isRoot ? 'var(--xp-purple)' : 'var(--xp-cyan)'} 
              style={{ background: 'var(--xp-bg-surface)', border: '1px solid var(--xp-border-default)', borderRadius: 'var(--xp-radius-md)' }} 
              maskColor="var(--xp-bg-void)" 
            />
          </ReactFlow>
        )}
        
        {/* Node Detail Panel */}
        {selectedNodeData && (
          <div className="xp-animate-slide-right" style={{
            width: '320px', flexShrink: 0, background: 'var(--xp-bg-surface)', 
            borderLeft: '1px solid var(--xp-border-default)', padding: 'var(--xp-space-6)',
            overflowY: 'auto', display: 'flex', flexDirection: 'column'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--xp-space-6)' }}>
              <h3 style={{ margin: 0, fontSize: 'var(--xp-text-lg)', color: 'var(--xp-text-primary)' }}>Node Details</h3>
              <button onClick={() => setSelectedNodeData(null)} style={{ background: 'none', border: 'none', color: 'var(--xp-text-muted)', cursor: 'pointer' }}><X size={16}/></button>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-4)' }}>
              <div>
                <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>Type / Intent</div>
                <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-primary)', marginTop: '4px', fontWeight: 600 }}>{selectedNodeData.action_type || selectedNodeData.intent}</div>
              </div>
              
              {selectedNodeData.face_value && (
                <div>
                  <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>Face Value</div>
                  <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-secondary)', marginTop: '4px', wordBreak: 'break-all' }}>{selectedNodeData.face_value}</div>
                </div>
              )}
              
              {selectedNodeData.url && (
                <div>
                  <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>URL Context</div>
                  <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-cyan)', marginTop: '4px', wordBreak: 'break-all' }}>{selectedNodeData.url}</div>
                </div>
              )}

              <div>
                <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase' }}>Tier</div>
                <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-purple)', marginTop: '4px', fontFamily: 'var(--xp-font-mono)' }}>{selectedNodeData.tier || 'Unknown'}</div>
              </div>
              
              {selectedNodeData.parameters && (
                <div style={{ marginTop: '8px' }}>
                  <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', textTransform: 'uppercase', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Code2 size={14} /> Parameters
                  </div>
                  <div style={{ 
                    background: 'var(--xp-bg-void)', padding: '12px', borderRadius: 'var(--xp-radius-md)',
                    fontFamily: 'var(--xp-font-mono)', fontSize: '11px', color: 'var(--xp-text-secondary)',
                    overflowX: 'auto', border: '1px solid var(--xp-border-subtle)'
                  }}>
                    <pre style={{ margin: 0 }}>{JSON.stringify(selectedNodeData.parameters, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
