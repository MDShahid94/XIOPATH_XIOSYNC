import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Activity, CheckCircle, XCircle, Clock } from 'lucide-react';

const API_URL = "http://localhost:8000/api/v1";

export default function TaskTracker({ sessionId }) {
  const [statusData, setStatusData] = useState(null);

  useEffect(() => {
    if (!sessionId) return;

    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API_URL}/agent/status/${sessionId}`);
        setStatusData(res.data);
        if (res.data.status === 'completed' || res.data.status === 'failed') {
          clearInterval(interval);
        }
      } catch (err) {
        console.error("Status check failed", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [sessionId]);

  if (!sessionId) {
    return (
      <div className="glass-panel">
        <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={20} /> Live Task Tracker
        </h3>
        <p style={{ color: 'var(--text-muted)' }}>Launch an agent to track its progress.</p>
      </div>
    );
  }

  return (
    <div className="glass-panel">
      <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Activity size={20} /> Live Task Tracker
      </h3>
      
      {!statusData ? (
        <p style={{ color: 'var(--text-muted)' }}>Polling status...</p>
      ) : (
        <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {statusData.status === 'queued' && <Clock color="var(--primary)" />}
            {statusData.status === 'running' && <Activity color="var(--primary)" className="spinner" />}
            {statusData.status === 'completed' && <CheckCircle color="#10b981" />}
            {statusData.status === 'failed' && <XCircle color="#ef4444" />}
            
            <strong style={{ textTransform: 'uppercase', letterSpacing: '1px' }}>
              {statusData.status}
            </strong>
          </div>
          
          <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
            <div><strong>Session:</strong> {sessionId}</div>
            <div><strong>URL:</strong> {statusData.url}</div>
            <div><strong>Intent:</strong> {statusData.intent}</div>
            {statusData.error && (
              <div style={{ color: '#ef4444', marginTop: '8px' }}>
                <strong>Error:</strong> {statusData.error}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
