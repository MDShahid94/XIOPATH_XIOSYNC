/**
 * XIOPATH — Execute Page (v5.1)
 * ===============================
 * High-tech execution console with real-time log streaming.
 * Fixed: removed duplicate WebSocket, replaced hardcoded hex colors
 * with design tokens, fixed interval leak, fixed stale closure.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Play, StopCircle, Terminal, Activity, CheckCircle, XCircle,
  Clock, Loader2, Cpu
} from 'lucide-react';
import { workflowsAPI } from '../../lib/api-v2';
import useAuthStore from '../../stores/authStore';
import useToastStore from '../../stores/toastStore';

// ─── Status Color Map (all design tokens) ───────────────────
const STATUS_COLORS = {
  running:   { bg: 'var(--xp-cyan-muted)',    fg: 'var(--xp-cyan)',    border: 'rgba(6,214,160,0.25)' },
  completed: { bg: 'var(--xp-success-bg)',     fg: 'var(--xp-success)', border: 'rgba(6,214,160,0.25)' },
  failed:    { bg: 'var(--xp-danger-bg)',      fg: 'var(--xp-danger)',  border: 'rgba(239,68,68,0.25)' },
  idle:      { bg: 'rgba(255,255,255,0.04)',   fg: 'var(--xp-text-muted)', border: 'var(--xp-border-subtle)' },
};

// ─── Terminal Log Colors (design tokens) ────────────────────
const LOG_COLORS = {
  info:    'var(--xp-text-secondary)',
  system:  'var(--xp-cyan)',
  success: 'var(--xp-success)',
  error:   'var(--xp-danger)',
  warning: 'var(--xp-warning)',
};

export default function ExecutePage() {
  const { token } = useAuthStore();
  const addToast = useToastStore((s) => s.addToast);

  // Data State
  const [workflows, setWorkflows] = useState([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState('');
  const [inputData, setInputData] = useState('{\n  "target": "example.com"\n}');

  // Execution State
  const [execStatus, setExecStatus] = useState('idle');
  const activeExecIdRef = useRef(null);
  const [activeExecIdDisplay, setActiveExecIdDisplay] = useState(null);
  const [logs, setLogs] = useState([
    { time: new Date(), msg: 'SYSTEM V5.0 READY', type: 'system' },
    { time: new Date(), msg: 'Awaiting execution dispatch...', type: 'info' },
  ]);

  const terminalEndRef = useRef(null);
  const wsRef = useRef(null);
  const pollRef = useRef(null);

  // Auto-scroll terminal
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Fetch workflows
  useEffect(() => {
    workflowsAPI.list().then(res => {
      const wfs = res.data?.workflows || [];
      setWorkflows(wfs);
      if (wfs.length > 0) setSelectedWorkflow(wfs[0].id);
    }).catch(err => {
      appendLog(`Failed to load workflows: ${err.message}`, 'error');
    });
  }, []);

  // Single WebSocket connection (no duplication)
  useEffect(() => {
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const apiHost = import.meta.env.VITE_API_URL
      ? new URL(import.meta.env.VITE_API_URL).host
      : (window.location.host === 'localhost:5173' ? 'localhost:8000' : window.location.host);
    const wsUrl = `${protocol}//${apiHost}/api/v1/ws/dashboard?token=${token}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => appendLog('WebSocket telemetry channel established.', 'system');

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Use ref to avoid stale closure
          if (data.type === 'execution_log' && data.execution_id === activeExecIdRef.current) {
            appendLog(data.message, data.level || 'info');
            if (data.status) setExecStatus(data.status);
          } else if (data.type === 'system') {
            appendLog(`[SYSTEM] ${data.message}`, 'system');
          }
        } catch (e) { /* ignore parse errors */ }
      };

      ws.onerror = () => appendLog('WebSocket telemetry connection error.', 'error');
      ws.onclose = () => appendLog('WebSocket telemetry channel closed.', 'system');
    } catch (e) {
      appendLog(`WS Setup Error: ${e.message}`, 'error');
    }

    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [token]); // Only reconnect when token changes, NOT on activeExecId

  // Cleanup poll interval on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const appendLog = useCallback((msg, type = 'info') => {
    setLogs(prev => [...prev, { time: new Date(), msg, type }]);
  }, []);

  const handleExecute = async () => {
    if (!selectedWorkflow) return;

    let parsedInput = {};
    try {
      parsedInput = JSON.parse(inputData);
    } catch (e) {
      addToast('Invalid JSON input data', 'error');
      return;
    }

    setExecStatus('running');
    setLogs([{ time: new Date(), msg: 'Initializing execution sequence...', type: 'system' }]);
    activeExecIdRef.current = null;
    setActiveExecIdDisplay(null);

    // Clear previous poll
    if (pollRef.current) clearInterval(pollRef.current);

    try {
      appendLog(`Dispatching workflow [${selectedWorkflow}] to core engine...`, 'info');
      const res = await workflowsAPI.execute(selectedWorkflow, {
        input_data: parsedInput,
        environment: 'production',
      });

      const execId = res.data.execution_id;
      activeExecIdRef.current = execId;
      setActiveExecIdDisplay(execId);
      appendLog(`Execution ID generated: ${execId}`, 'success');
      appendLog('Awaiting worker allocation...', 'info');

      // Fallback polling with proper cleanup
      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await workflowsAPI.getExecution(execId);
          const currentStatus = statusRes.data.status;
          setExecStatus(currentStatus);

          if (currentStatus === 'completed' || currentStatus === 'failed') {
            clearInterval(pollRef.current);
            pollRef.current = null;
            appendLog(
              `Execution finished: ${currentStatus.toUpperCase()}`,
              currentStatus === 'completed' ? 'success' : 'error'
            );
          }
        } catch (e) { /* ignore poll errors */ }
      }, 3000);
    } catch (err) {
      appendLog(`Dispatch failed: ${err.message}`, 'error');
      setExecStatus('failed');
      addToast('Execution dispatch failed: ' + err.message, 'error');
    }
  };

  const handleStop = async () => {
    if (!activeExecIdRef.current) return;
    appendLog(`Sending cancellation signal to [${activeExecIdRef.current}]...`, 'warning');
    try {
      await workflowsAPI.cancelExecution(activeExecIdRef.current);
      setExecStatus('failed');
      appendLog('Execution cancelled by operator.', 'error');
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    } catch (err) {
      appendLog(`Cancel failed: ${err.message}`, 'error');
    }
  };

  const statusColors = STATUS_COLORS[execStatus] || STATUS_COLORS.idle;

  return (
    <div className="xp-animate-fade-in" style={{ padding: 'var(--xp-space-8)', maxWidth: 1400, margin: '0 auto', display: 'flex', gap: 'var(--xp-space-6)', height: 'calc(100vh - 100px)' }}>

      {/* ─── Left Panel: Controls ────────────────────────── */}
      <div style={{ width: 380, display: 'flex', flexDirection: 'column', gap: 'var(--xp-space-6)', flexShrink: 0 }}>

        <div className="xp-card">
          <h2 style={{ fontSize: 'var(--xp-text-lg)', fontWeight: 700, color: 'var(--xp-text-primary)', marginBottom: 'var(--xp-space-4)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Cpu size={20} style={{ color: 'var(--xp-cyan)' }} /> Dispatch Engine
          </h2>

          <div className="xp-field" style={{ marginBottom: 'var(--xp-space-4)' }}>
            <label className="xp-label">Target Workflow</label>
            <select className="xp-select" value={selectedWorkflow} onChange={e => setSelectedWorkflow(e.target.value)} disabled={execStatus === 'running'}>
              {workflows.length === 0 ? (
                <option value="">No workflows available</option>
              ) : (
                workflows.map(wf => (
                  <option key={wf.id} value={wf.id}>{wf.name} ({wf.id.slice(0, 6)})</option>
                ))
              )}
            </select>
          </div>

          <div className="xp-field" style={{ marginBottom: 'var(--xp-space-6)' }}>
            <label className="xp-label">Input Payload (JSON)</label>
            <textarea
              className="xp-textarea"
              style={{ height: 140, fontFamily: 'var(--xp-font-mono)', fontSize: 12, resize: 'none' }}
              value={inputData}
              onChange={e => setInputData(e.target.value)}
              disabled={execStatus === 'running'}
            />
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <button className="xp-btn xp-btn-primary" style={{ flex: 1 }} onClick={handleExecute} disabled={execStatus === 'running' || !selectedWorkflow}>
              {execStatus === 'running' ? <Loader2 size={16} className="xp-animate-spin" /> : <Play size={16} />}
              {execStatus === 'running' ? 'Executing…' : 'Launch Sequence'}
            </button>
            <button
              className={`xp-btn ${execStatus === 'running' ? 'xp-btn-danger' : 'xp-btn-ghost'}`}
              style={{ width: 48, padding: 0, display: 'flex', justifyContent: 'center' }}
              onClick={handleStop}
              disabled={execStatus !== 'running'}
              title="Force Stop"
            >
              <StopCircle size={20} />
            </button>
          </div>
        </div>

        {/* Status Card */}
        <div className="xp-card">
          <h3 className="xp-label" style={{ marginBottom: 16 }}>Telemetry Status</h3>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 48, height: 48, borderRadius: 'var(--xp-radius-lg)',
              background: statusColors.bg, color: statusColors.fg,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: `1px solid ${statusColors.border}`,
            }}>
              {execStatus === 'running' ? <Activity size={24} /> :
               execStatus === 'completed' ? <CheckCircle size={24} /> :
               execStatus === 'failed' ? <XCircle size={24} /> :
               <Clock size={24} />}
            </div>
            <div>
              <div style={{ fontSize: 'var(--xp-text-lg)', fontWeight: 700, color: 'var(--xp-text-primary)', textTransform: 'capitalize' }}>
                {execStatus}
              </div>
              <div style={{ fontSize: 12, color: 'var(--xp-text-muted)', fontFamily: 'var(--xp-font-mono)' }}>
                {activeExecIdDisplay ? activeExecIdDisplay.slice(0, 12) : 'No active execution'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ─── Right Panel: Terminal ────────────────────────── */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        background: 'var(--xp-bg-void)', border: '1px solid var(--xp-border-strong)',
        borderRadius: 'var(--xp-radius-lg)', overflow: 'hidden',
        boxShadow: 'var(--xp-shadow-xl)',
      }}>
        {/* Terminal Header */}
        <div style={{
          background: 'var(--xp-bg-base)', padding: '12px 16px',
          borderBottom: '1px solid var(--xp-border-default)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <Terminal size={16} style={{ color: 'var(--xp-text-muted)' }} />
          <span style={{ fontSize: 13, color: 'var(--xp-text-secondary)', fontWeight: 600, fontFamily: 'var(--xp-font-mono)' }}>
            tty1 — xio-core-orchestrator
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--xp-danger)' }} />
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--xp-warning)' }} />
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--xp-success)' }} />
          </div>
        </div>

        {/* Terminal Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 16, fontFamily: 'var(--xp-font-mono)', fontSize: 13, lineHeight: 1.6 }}>
          {logs.map((log, i) => {
            const color = LOG_COLORS[log.type] || LOG_COLORS.info;
            const timeStr = log.time.toISOString().split('T')[1].slice(0, 12);
            return (
              <div key={i} style={{ display: 'flex', gap: 12, marginBottom: 6, opacity: 0.9 }}>
                <span style={{ color: 'var(--xp-text-disabled)', flexShrink: 0 }}>[{timeStr}]</span>
                <span style={{ color, wordBreak: 'break-all' }}>{log.msg}</span>
              </div>
            );
          })}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  );
}
