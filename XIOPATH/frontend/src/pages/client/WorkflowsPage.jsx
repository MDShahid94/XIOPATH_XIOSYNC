/**
 * XIOPATH — Workflow Studio v3 (Production-Grade)
 * ==================================================
 * Full visual DAG workflow editor with:
 * - Categorized node library (Actions, Logic, Flow Control, Data)
 * - Built-in logic nodes (Conditional, Loop, Switch, Delay, Error Handler)
 * - Canvas toolbar with save/delete/fork/export
 * - Node inspector panel (side-panel config on selection)
 * - Context menu (right-click), keyboard shortcuts (Delete)
 * - Drag-from-library-to-canvas support
 * - Workflow lifecycle management
 */
import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import {
  ReactFlow, Background, Controls, MiniMap,
  addEdge, useNodesState, useEdgesState,
  Handle, Position, Panel, useReactFlow, ReactFlowProvider
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import '../../styles/workflow-studio.css';
import {
  Network, Plus, Save, Trash2, Play, GitBranch, Zap,
  Activity, Settings, Eye, Globe, MousePointer,
  FolderOpen, ShieldCheck, Search, X, Copy, Download,
  RotateCcw, Repeat, Timer, AlertTriangle, ArrowRightLeft,
  Filter, Database, Variable, Webhook, Radio, Layers,
  ChevronRight, MoreVertical, Maximize2, Grid3x3,
  SplitSquareHorizontal, Merge, Shield
} from 'lucide-react';
import { typesAPI, workflowsAPI } from '../../lib/api-v2';
import useToastStore from '../../stores/toastStore';

// ═══════════════════════════════════════════════════════════
// BUILT-IN NODE DEFINITIONS
// ═══════════════════════════════════════════════════════════

const BUILTIN_LOGIC_NODES = [
  {
    type_id: 'conditional',
    label: 'Conditional (If / Else)',
    description: 'Branch based on a condition expression',
    icon: GitBranch,
    color: 'var(--xp-warning)',
    category: 'logic',
    nodeStyle: 'logic',
    config: { condition: '', trueLabel: 'Yes', falseLabel: 'No' },
  },
  {
    type_id: 'loop_foreach',
    label: 'Loop (For Each)',
    description: 'Iterate over a collection of items',
    icon: Repeat,
    color: 'var(--xp-warning)',
    category: 'logic',
    nodeStyle: 'logic',
    config: { collection: '', itemVariable: 'item' },
  },
  {
    type_id: 'loop_while',
    label: 'While Loop',
    description: 'Repeat while a condition is true',
    icon: RotateCcw,
    color: 'var(--xp-warning)',
    category: 'logic',
    nodeStyle: 'logic',
    config: { condition: '', maxIterations: 100 },
  },
  {
    type_id: 'switch_case',
    label: 'Switch / Case',
    description: 'Multi-way branch based on a value',
    icon: ArrowRightLeft,
    color: 'var(--xp-warning)',
    category: 'logic',
    nodeStyle: 'logic',
    config: { expression: '', cases: ['case_1', 'default'] },
  },
];

const BUILTIN_FLOW_NODES = [
  {
    type_id: 'delay',
    label: 'Delay / Wait',
    description: 'Pause execution for a duration',
    icon: Timer,
    color: 'var(--xp-purple)',
    category: 'flow',
    nodeStyle: 'flow',
    config: { durationMs: 1000 },
  },
  {
    type_id: 'parallel',
    label: 'Parallel Branch',
    description: 'Execute multiple branches simultaneously',
    icon: SplitSquareHorizontal,
    color: 'var(--xp-purple)',
    category: 'flow',
    nodeStyle: 'flow',
    config: { branches: 2 },
  },
  {
    type_id: 'merge',
    label: 'Merge',
    description: 'Merge parallel branches back together',
    icon: Merge,
    color: 'var(--xp-purple)',
    category: 'flow',
    nodeStyle: 'flow',
    config: { strategy: 'wait_all' },
  },
  {
    type_id: 'error_handler',
    label: 'Error Handler (Try/Catch)',
    description: 'Catch and handle errors in the workflow',
    icon: Shield,
    color: 'var(--xp-danger)',
    category: 'flow',
    nodeStyle: 'flow',
    config: { retryCount: 0, fallbackAction: '' },
  },
];

const BUILTIN_DATA_NODES = [
  {
    type_id: 'transform',
    label: 'Transform',
    description: 'Transform data between steps',
    icon: Layers,
    color: 'var(--xp-blue)',
    category: 'data',
    nodeStyle: 'action',
    config: { expression: '' },
  },
  {
    type_id: 'filter',
    label: 'Filter',
    description: 'Filter items from a collection',
    icon: Filter,
    color: 'var(--xp-blue)',
    category: 'data',
    nodeStyle: 'action',
    config: { predicate: '' },
  },
  {
    type_id: 'variable_set',
    label: 'Set Variable',
    description: 'Store a value in a workflow variable',
    icon: Variable,
    color: 'var(--xp-blue)',
    category: 'data',
    nodeStyle: 'action',
    config: { name: '', value: '' },
  },
];

const BUILTIN_INTEGRATION_NODES = [
  {
    type_id: 'webhook_trigger',
    label: 'Webhook Trigger',
    description: 'Start workflow on incoming webhook',
    icon: Webhook,
    color: 'var(--xp-success)',
    category: 'integrations',
    nodeStyle: 'trigger',
    config: { path: '/webhook', method: 'POST' },
  },
  {
    type_id: 'event_listener',
    label: 'Event Listener',
    description: 'Listen for system events',
    icon: Radio,
    color: 'var(--xp-success)',
    category: 'integrations',
    nodeStyle: 'trigger',
    config: { eventType: '' },
  },
];

// ═══════════════════════════════════════════════════════════
// CUSTOM NODE COMPONENT
// ═══════════════════════════════════════════════════════════

function WorkflowNode({ data, selected }) {
  const Icon = data.icon || Zap;
  const nodeStyle = data.nodeStyle || 'action';
  const nodeClass = `wfs-node wfs-node-${nodeStyle} ${selected ? 'selected' : ''}`;

  return (
    <div className={nodeClass}>
      <Handle type="target" position={Position.Top}
        style={{ background: 'var(--xp-purple)', width: 10, height: 10, border: '2px solid var(--xp-bg-surface)' }}
      />

      <div className="wfs-node-header">
        <div className="wfs-node-icon" style={{
          background: `${data.color || 'var(--xp-cyan)'}15`,
          border: `1px solid ${data.color || 'var(--xp-cyan)'}40`,
        }}>
          <Icon size={16} style={{ color: data.color || 'var(--xp-cyan)' }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="wfs-node-title">{data.label}</div>
          <div className="wfs-node-subtitle">{data.type_id || 'custom'}</div>
        </div>
      </div>

      {data.description && (
        <div className="wfs-node-desc">{data.description}</div>
      )}

      {data.is_builtin && (
        <div className="wfs-node-badge" style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--xp-text-muted)' }}>
          <ShieldCheck size={10} /> BUILT-IN
        </div>
      )}

      {/* Conditional node: two output handles */}
      {data.type_id === 'conditional' ? (
        <>
          <Handle type="source" position={Position.Bottom} id="true"
            style={{ background: 'var(--xp-success)', width: 10, height: 10, border: '2px solid var(--xp-bg-surface)', left: '30%' }}
          />
          <Handle type="source" position={Position.Bottom} id="false"
            style={{ background: 'var(--xp-danger)', width: 10, height: 10, border: '2px solid var(--xp-bg-surface)', left: '70%' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 9, color: 'var(--xp-text-muted)' }}>
            <span style={{ color: 'var(--xp-success)' }}>✓ True</span>
            <span style={{ color: 'var(--xp-danger)' }}>✗ False</span>
          </div>
        </>
      ) : data.type_id === 'switch_case' ? (
        <>
          {(data.config?.cases || ['case_1', 'default']).map((c, i, arr) => (
            <Handle key={c} type="source" position={Position.Bottom} id={c}
              style={{
                background: c === 'default' ? 'var(--xp-text-muted)' : 'var(--xp-cyan)',
                width: 8, height: 8,
                border: '2px solid var(--xp-bg-surface)',
                left: `${((i + 1) / (arr.length + 1)) * 100}%`,
              }}
            />
          ))}
        </>
      ) : (
        <Handle type="source" position={Position.Bottom}
          style={{ background: 'var(--xp-cyan)', width: 10, height: 10, border: '2px solid var(--xp-bg-surface)' }}
        />
      )}
    </div>
  );
}

const nodeTypes = { workflow: WorkflowNode };

// ═══════════════════════════════════════════════════════════
// NODE INSPECTOR PANEL
// ═══════════════════════════════════════════════════════════

function InspectorPanel({ node, onUpdate, onClose }) {
  if (!node) return null;
  const data = node.data;

  const handleChange = (field, value) => {
    onUpdate(node.id, { ...data, config: { ...data.config, [field]: value } });
  };

  return (
    <div className="wfs-inspector">
      <div className="wfs-inspector-header">
        <div className="wfs-inspector-title">
          <Settings size={16} />
          Node Inspector
        </div>
        <button className="xp-btn xp-btn-ghost xp-btn-icon xp-btn-sm" onClick={onClose}>
          <X size={14} />
        </button>
      </div>
      <div className="wfs-inspector-body">
        {/* Identity */}
        <div className="wfs-inspector-section">
          <div className="wfs-inspector-section-title">Identity</div>
          <div className="xp-field" style={{ marginBottom: 'var(--xp-space-3)' }}>
            <label className="xp-label">Node Name</label>
            <input className="xp-input" value={data.label || ''}
              onChange={(e) => onUpdate(node.id, { ...data, label: e.target.value })}
            />
          </div>
          <div className="xp-field" style={{ marginBottom: 'var(--xp-space-3)' }}>
            <label className="xp-label">Description</label>
            <textarea className="xp-textarea" rows={2} value={data.description || ''}
              onChange={(e) => onUpdate(node.id, { ...data, description: e.target.value })}
              style={{ minHeight: 60 }}
            />
          </div>
          <div className="xp-field">
            <label className="xp-label">Type</label>
            <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-secondary)', fontFamily: 'var(--xp-font-mono)' }}>
              {data.type_id}
            </div>
          </div>
        </div>

        {/* Configuration (dynamic per node type) */}
        {data.config && Object.keys(data.config).length > 0 && (
          <div className="wfs-inspector-section">
            <div className="wfs-inspector-section-title">Configuration</div>
            {Object.entries(data.config).map(([key, value]) => (
              <div key={key} className="xp-field" style={{ marginBottom: 'var(--xp-space-3)' }}>
                <label className="xp-label">{key.replace(/_/g, ' ')}</label>
                {typeof value === 'number' ? (
                  <input className="xp-input" type="number" value={value}
                    onChange={(e) => handleChange(key, Number(e.target.value))}
                  />
                ) : Array.isArray(value) ? (
                  <input className="xp-input" value={value.join(', ')}
                    onChange={(e) => handleChange(key, e.target.value.split(',').map(s => s.trim()))}
                    placeholder="Comma-separated values"
                  />
                ) : (
                  <input className="xp-input" value={value}
                    onChange={(e) => handleChange(key, e.target.value)}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        {/* Node Meta */}
        <div className="wfs-inspector-section">
          <div className="wfs-inspector-section-title">Meta</div>
          <div style={{ fontSize: 'var(--xp-text-xs)', color: 'var(--xp-text-muted)', fontFamily: 'var(--xp-font-mono)' }}>
            ID: {node.id}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// CONTEXT MENU
// ═══════════════════════════════════════════════════════════

function ContextMenu({ x, y, nodeId, onAction, onClose }) {
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  return (
    <div className="wfs-context-menu" ref={menuRef} style={{ left: x, top: y }}>
      <button className="wfs-context-item" onClick={() => onAction('duplicate')}>
        <Copy size={14} /> Duplicate
      </button>
      <button className="wfs-context-item" onClick={() => onAction('inspect')}>
        <Settings size={14} /> Inspect
      </button>
      <div className="wfs-context-sep" />
      <button className="wfs-context-item danger" onClick={() => onAction('delete')}>
        <Trash2 size={14} /> Delete
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN STUDIO COMPONENT
// ═══════════════════════════════════════════════════════════

function WorkflowStudioInner() {
  const addToast = useToastStore((s) => s.addToast);
  const { fitView } = useReactFlow();

  // Registry Data
  const [registryNodes, setRegistryNodes] = useState([]);

  // Workflows List
  const [savedWorkflows, setSavedWorkflows] = useState([]);
  const [activeWorkflow, setActiveWorkflow] = useState(null);
  const [activeWorkflowData, setActiveWorkflowData] = useState(null);

  // Canvas State
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [workflowName, setWorkflowName] = useState('Untitled Workflow');
  const [saving, setSaving] = useState(false);

  // UI State
  const [selectedNode, setSelectedNode] = useState(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState(null);
  const [librarySearch, setLibrarySearch] = useState('');
  const reactFlowWrapper = useRef(null);

  // Fetch Types from Registry (action_type)
  useEffect(() => {
    typesAPI.list('action_type').then(res => {
      const actions = res.data?.types || [];
      const templates = actions.map(act => ({
        type_id: act.name,
        label: act.display_name || act.name,
        description: act.description,
        is_builtin: act.is_builtin,
        icon: act.name.includes('navigate') ? Globe :
              act.name.includes('click') ? MousePointer :
              act.name.includes('extract') ? Eye :
              act.name.includes('type') || act.name.includes('input') ? Activity : Zap,
        color: act.name.includes('navigate') ? 'var(--xp-cyan)' :
               act.name.includes('click') ? 'var(--xp-purple)' :
               act.name.includes('condition') ? 'var(--xp-warning)' : 'var(--xp-blue)',
        category: 'actions',
        nodeStyle: 'action',
        config: {},
      }));
      setRegistryNodes(templates);
    }).catch(() => {
      // Registry unavailable — still show built-in nodes
    });

    fetchWorkflowsList();
  }, []);

  const fetchWorkflowsList = async () => {
    try {
      const res = await workflowsAPI.list();
      setSavedWorkflows(res.data?.workflows || []);
    } catch (err) {
      console.error(err);
    }
  };

  // ─── All node templates organized by category ─────────

  const allNodeTemplates = useMemo(() => {
    return [
      ...registryNodes,
      ...BUILTIN_LOGIC_NODES,
      ...BUILTIN_FLOW_NODES,
      ...BUILTIN_DATA_NODES,
      ...BUILTIN_INTEGRATION_NODES,
    ];
  }, [registryNodes]);

  const filteredTemplates = useMemo(() => {
    if (!librarySearch.trim()) return allNodeTemplates;
    const q = librarySearch.toLowerCase();
    return allNodeTemplates.filter(n =>
      n.label.toLowerCase().includes(q) || n.type_id.toLowerCase().includes(q)
    );
  }, [allNodeTemplates, librarySearch]);

  const groupedTemplates = useMemo(() => {
    const groups = {};
    for (const node of filteredTemplates) {
      const cat = node.category || 'actions';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(node);
    }
    return groups;
  }, [filteredTemplates]);

  const CATEGORY_META = {
    actions:      { label: 'Actions',       icon: Zap,                      color: 'var(--xp-cyan)' },
    logic:        { label: 'Logic',         icon: GitBranch,                color: 'var(--xp-warning)' },
    flow:         { label: 'Flow Control',  icon: SplitSquareHorizontal,    color: 'var(--xp-purple)' },
    data:         { label: 'Data',          icon: Database,                 color: 'var(--xp-blue)' },
    integrations: { label: 'Integrations',  icon: Webhook,                  color: 'var(--xp-success)' },
  };

  // ─── Workflow CRUD ────────────────────────────────────

  const loadWorkflow = async (wf) => {
    try {
      const res = await workflowsAPI.get(wf.id);
      const data = res.data;
      setActiveWorkflow(data.id);
      setActiveWorkflowData(data);
      setWorkflowName(data.name || 'Untitled Workflow');
      setNodes(data.metadata?.layout?.nodes || []);
      setEdges(data.metadata?.layout?.edges || []);
      setSelectedNode(null);
      setInspectorOpen(false);
    } catch (err) {
      addToast('Failed to load workflow', 'error');
    }
  };

  const createNew = () => {
    setActiveWorkflow(null);
    setActiveWorkflowData(null);
    setWorkflowName('New Workflow');
    setNodes([{
      id: 'start', type: 'workflow', position: { x: 300, y: 80 },
      data: { label: 'Start Trigger', type_id: 'trigger', icon: Play, color: 'var(--xp-success)', nodeStyle: 'trigger', config: {} },
    }]);
    setEdges([]);
    setSelectedNode(null);
    setInspectorOpen(false);
  };

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      name: workflowName,
      status: activeWorkflowData?.status || 'draft',
      metadata: { layout: { nodes, edges } },
    };

    try {
      if (activeWorkflow) {
        await workflowsAPI.update(activeWorkflow, payload);
      } else {
        const res = await workflowsAPI.create(payload);
        setActiveWorkflow(res.data.id);
        setActiveWorkflowData(res.data);
      }
      fetchWorkflowsList();
      addToast('Workflow saved successfully', 'success');
    } catch (err) {
      addToast('Failed to save: ' + err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!activeWorkflow) return;
    try {
      await workflowsAPI.delete(activeWorkflow);
      setActiveWorkflow(null);
      setActiveWorkflowData(null);
      setNodes([]);
      setEdges([]);
      setWorkflowName('Untitled Workflow');
      fetchWorkflowsList();
      addToast('Workflow deleted', 'info');
    } catch (err) {
      addToast('Failed to delete: ' + err.message, 'error');
    }
  };

  const handleFork = async () => {
    if (!activeWorkflow) return;
    try {
      const res = await workflowsAPI.fork(activeWorkflow, { name: workflowName + ' (Copy)' });
      fetchWorkflowsList();
      addToast('Workflow forked successfully', 'success');
      if (res.data?.id) loadWorkflow(res.data);
    } catch (err) {
      addToast('Failed to fork: ' + err.message, 'error');
    }
  };

  const handleExport = () => {
    const data = JSON.stringify({ name: workflowName, nodes, edges }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${workflowName.replace(/\s+/g, '_').toLowerCase()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    addToast('Workflow exported as JSON', 'success');
  };

  // ─── Canvas Interactions ──────────────────────────────

  const onConnect = useCallback((params) => {
    setEdges((eds) => addEdge({
      ...params,
      animated: true,
      style: { stroke: 'var(--xp-cyan)', strokeWidth: 2 },
    }, eds));
  }, [setEdges]);

  const addNodeToCanvas = useCallback((template, position) => {
    const id = crypto.randomUUID();
    const pos = position || { x: 300, y: (nodes.length + 1) * 160 };
    const newNode = {
      id,
      type: 'workflow',
      position: pos,
      data: { ...template },
    };
    setNodes((nds) => [...nds, newNode]);
  }, [nodes.length, setNodes]);

  // Drag from library to canvas
  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    const templateJSON = e.dataTransfer.getData('application/xiopath-node');
    if (!templateJSON) return;

    const template = JSON.parse(templateJSON);
    const bounds = reactFlowWrapper.current?.getBoundingClientRect();
    if (!bounds) return;

    const position = {
      x: e.clientX - bounds.left - 110,
      y: e.clientY - bounds.top - 30,
    };
    addNodeToCanvas(template, position);
  }, [addNodeToCanvas]);

  const onDragStart = (e, template) => {
    e.dataTransfer.setData('application/xiopath-node', JSON.stringify(template));
    e.dataTransfer.effectAllowed = 'move';
  };

  // Node selection → open inspector
  const onNodeClick = useCallback((_, node) => {
    setSelectedNode(node);
    setInspectorOpen(true);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setInspectorOpen(false);
    setContextMenu(null);
  }, []);

  // Right-click context menu
  const onNodeContextMenu = useCallback((e, node) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, nodeId: node.id });
    setSelectedNode(node);
  }, []);

  const handleContextAction = (action) => {
    if (!contextMenu) return;
    const nodeId = contextMenu.nodeId;

    if (action === 'delete') {
      setNodes((nds) => nds.filter(n => n.id !== nodeId));
      setEdges((eds) => eds.filter(e => e.source !== nodeId && e.target !== nodeId));
      if (selectedNode?.id === nodeId) {
        setSelectedNode(null);
        setInspectorOpen(false);
      }
    } else if (action === 'duplicate') {
      const source = nodes.find(n => n.id === nodeId);
      if (source) {
        addNodeToCanvas({ ...source.data }, {
          x: source.position.x + 40,
          y: source.position.y + 60,
        });
      }
    } else if (action === 'inspect') {
      setInspectorOpen(true);
    }
    setContextMenu(null);
  };

  // Keyboard: Delete selected nodes
  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNode && !e.target.closest('input, textarea')) {
        setNodes((nds) => nds.filter(n => n.id !== selectedNode.id));
        setEdges((eds) => eds.filter(e => e.source !== selectedNode.id && e.target !== selectedNode.id));
        setSelectedNode(null);
        setInspectorOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedNode, setNodes, setEdges]);

  // Inspector updates
  const handleNodeUpdate = (nodeId, newData) => {
    setNodes((nds) => nds.map(n =>
      n.id === nodeId ? { ...n, data: newData } : n
    ));
    if (selectedNode?.id === nodeId) {
      setSelectedNode(prev => ({ ...prev, data: newData }));
    }
  };

  // Status helpers
  const getStatusClass = (status) => {
    if (status === 'active') return 'wfs-status wfs-status-active';
    if (status === 'archived') return 'wfs-status wfs-status-archived';
    return 'wfs-status wfs-status-draft';
  };

  return (
    <div className="wfs-layout xp-animate-fade-in">

      {/* ─── Left Sidebar: Workflows List ───────────────────── */}
      <div className="wfs-sidebar">
        <div className="wfs-sidebar-header">
          <h2 className="wfs-sidebar-title">
            <Network size={20} style={{ color: 'var(--xp-cyan)' }} />
            Workflow Studio
          </h2>
          <button className="xp-btn xp-btn-primary" style={{ width: '100%' }} onClick={createNew}>
            <Plus size={16} /> New Workflow
          </button>
        </div>

        <div className="wfs-sidebar-body">
          <div className="wfs-sidebar-label">Saved Workflows</div>
          {savedWorkflows.length === 0 ? (
            <div style={{ fontSize: 'var(--xp-text-sm)', color: 'var(--xp-text-muted)', textAlign: 'center', marginTop: 20 }}>
              No workflows yet.
            </div>
          ) : (
            savedWorkflows.map(wf => (
              <div
                key={wf.id}
                className={`wfs-wf-item ${activeWorkflow === wf.id ? 'active' : ''}`}
                onClick={() => loadWorkflow(wf)}
              >
                <Network size={14} style={{ color: activeWorkflow === wf.id ? 'var(--xp-cyan)' : 'var(--xp-text-muted)', flexShrink: 0 }} />
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div className="wfs-wf-item-name">{wf.name}</div>
                  <div className="wfs-wf-item-id">{wf.id?.slice(0, 8)}</div>
                </div>
                <span className={getStatusClass(wf.status)}>{wf.status || 'draft'}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ─── Main Canvas Area ───────────────────────────────── */}
      <div className="wfs-canvas" ref={reactFlowWrapper} onDragOver={onDragOver} onDrop={onDrop}>
        {nodes.length === 0 && !activeWorkflow ? (
          <div className="wfs-canvas-empty">
            <Network size={56} className="wfs-canvas-empty-icon" />
            <div className="wfs-canvas-empty-text">Create or select a workflow to begin</div>
            <button className="xp-btn xp-btn-primary xp-btn-lg" onClick={createNew}>
              <Plus size={18} /> New Workflow
            </button>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onNodeContextMenu={onNodeContextMenu}
            nodeTypes={nodeTypes}
            fitView
            deleteKeyCode={null}
            style={{ background: 'var(--xp-bg-void)' }}
          >
            <Background color="var(--xp-border-strong)" gap={24} size={1.5} />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={n => n.data?.color || 'var(--xp-cyan)'}
              style={{ background: 'var(--xp-bg-surface)', border: '1px solid var(--xp-border-default)', borderRadius: 8 }}
            />

            {/* Canvas Toolbar */}
            <Panel position="top-left" style={{ margin: 16 }}>
              <div className="wfs-toolbar">
                <input
                  className="wfs-toolbar-name"
                  value={workflowName}
                  onChange={e => setWorkflowName(e.target.value)}
                />
                <div className="wfs-toolbar-sep" />
                {activeWorkflowData && (
                  <span className={getStatusClass(activeWorkflowData.status)}>
                    {activeWorkflowData.status || 'draft'}
                  </span>
                )}
                <div className="wfs-toolbar-sep" />
                <button className="wfs-toolbar-btn primary" onClick={handleSave} disabled={saving}>
                  <Save size={14} /> {saving ? 'Saving…' : 'Save'}
                </button>
                {activeWorkflow && (
                  <>
                    <button className="wfs-toolbar-btn" onClick={handleFork} data-tooltip="Fork">
                      <Copy size={14} /> Fork
                    </button>
                    <button className="wfs-toolbar-btn" onClick={handleExport} data-tooltip="Export JSON">
                      <Download size={14} />
                    </button>
                    <button className="wfs-toolbar-btn danger" onClick={handleDelete} data-tooltip="Delete">
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
                <div className="wfs-toolbar-sep" />
                <button className="wfs-toolbar-btn" onClick={() => fitView({ padding: 0.2, duration: 300 })} data-tooltip="Fit View">
                  <Maximize2 size={14} />
                </button>
              </div>
            </Panel>
          </ReactFlow>
        )}

        {/* Inspector Panel (overlaid on canvas) */}
        {inspectorOpen && selectedNode && (
          <InspectorPanel
            node={selectedNode}
            onUpdate={handleNodeUpdate}
            onClose={() => { setInspectorOpen(false); setSelectedNode(null); }}
          />
        )}

        {/* Context Menu */}
        {contextMenu && (
          <ContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            nodeId={contextMenu.nodeId}
            onAction={handleContextAction}
            onClose={() => setContextMenu(null)}
          />
        )}
      </div>

      {/* ─── Right Sidebar: Node Library ─────────────────────── */}
      <div className="wfs-library">
        <div className="wfs-library-header">
          <h3 className="wfs-library-title">
            <Layers size={16} /> Node Library
          </h3>
          <div className="wfs-library-search">
            <Search size={13} className="wfs-library-search-icon" />
            <input
              placeholder="Search nodes…"
              value={librarySearch}
              onChange={e => setLibrarySearch(e.target.value)}
            />
          </div>
        </div>

        <div className="wfs-library-body">
          {Object.entries(CATEGORY_META).map(([catKey, catMeta]) => {
            const items = groupedTemplates[catKey];
            if (!items || items.length === 0) return null;
            const CatIcon = catMeta.icon;

            return (
              <div key={catKey} className="wfs-lib-category">
                <div className="wfs-lib-cat-header">
                  <div className="wfs-lib-cat-icon" style={{ background: `${catMeta.color}20`, color: catMeta.color }}>
                    <CatIcon size={12} />
                  </div>
                  <span className="wfs-lib-cat-label">{catMeta.label}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--xp-text-muted)' }}>{items.length}</span>
                </div>
                {items.map(node => {
                  const NodeIcon = node.icon;
                  return (
                    <div
                      key={node.type_id}
                      className="wfs-lib-node"
                      draggable
                      onDragStart={(e) => onDragStart(e, node)}
                      onClick={() => addNodeToCanvas(node)}
                    >
                      <div className="wfs-lib-node-icon" style={{
                        background: `${node.color}15`,
                        border: `1px solid ${node.color}40`,
                        color: node.color,
                      }}>
                        <NodeIcon size={14} />
                      </div>
                      <div>
                        <div className="wfs-lib-node-label">{node.label}</div>
                        <div className="wfs-lib-node-type">{node.type_id}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}

          {filteredTemplates.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--xp-text-muted)', fontSize: 'var(--xp-text-sm)', marginTop: 20 }}>
              {librarySearch ? 'No matching nodes' : 'Loading registry…'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Wrap in ReactFlowProvider for useReactFlow() hook
export default function WorkflowsPage() {
  return (
    <ReactFlowProvider>
      <WorkflowStudioInner />
    </ReactFlowProvider>
  );
}
