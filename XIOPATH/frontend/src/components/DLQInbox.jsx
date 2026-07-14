import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { AlertOctagon, FileJson, Clock } from 'lucide-react';

const API_URL = "http://localhost:8000/api/v1";

export default function DLQInbox() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDLQ = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API_URL}/dlq/list`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setIncidents(res.data.incidents || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDLQ();
  }, []);

  return (
    <div className="glass-panel" style={{ borderColor: 'rgba(239, 68, 68, 0.3)' }}>
      <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444' }}>
        <AlertOctagon size={20} /> DLQ Incident Inbox
      </h3>
      <p style={{ color: 'var(--text-muted)', marginBottom: '16px' }}>
        Review automation failures dumped by the Circuit Breaker.
      </p>

      {loading ? (
        <p style={{ color: 'var(--text-muted)' }}>Loading incidents...</p>
      ) : error ? (
        <p style={{ color: '#ef4444' }}>Error loading DLQ: {error}</p>
      ) : incidents.length === 0 ? (
        <div style={{ 
          background: 'rgba(16, 185, 129, 0.1)', 
          padding: '16px', 
          borderRadius: '8px',
          color: '#10b981',
          textAlign: 'center'
        }}>
          No incidents reported. The system is healthy!
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {incidents.map(incident => (
            <div key={incident.id} style={{
              background: 'rgba(0, 0, 0, 0.2)',
              borderLeft: '4px solid #ef4444',
              padding: '16px',
              borderRadius: '8px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <strong style={{ fontSize: '1.1rem' }}>{incident.intent}</strong>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  <Clock size={14} />
                  {new Date(incident.timestamp).toLocaleString()}
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.9rem' }}>
                <div><strong>Domain:</strong> {incident.url}</div>
                <div><strong>Volatility:</strong> {incident.volatility_type}</div>
              </div>
              <details style={{ marginTop: '12px' }}>
                <summary style={{ cursor: 'pointer', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <FileJson size={16} /> View Context Dump
                </summary>
                <pre style={{ 
                  background: '#0f172a', 
                  padding: '12px', 
                  borderRadius: '4px', 
                  marginTop: '8px',
                  fontSize: '0.8rem',
                  overflowX: 'auto'
                }}>
                  {JSON.stringify(incident.context, null, 2)}
                </pre>
              </details>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
