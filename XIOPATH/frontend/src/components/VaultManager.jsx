import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { KeyRound, Plus, Lock } from 'lucide-react';

const API_URL = "http://localhost:8000/api/v1";

export default function VaultManager() {
  const [keys, setKeys] = useState([]);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');

  const fetchKeys = async () => {
    try {
      const res = await axios.get(`${API_URL}/vault/keys`);
      setKeys(res.data.keys || []);
    } catch (err) {
      console.error("Failed to fetch vault keys", err);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    setLoading(true);
    setStatus('Adding secret...');
    try {
      await axios.post(`${API_URL}/vault/add`, {
        key: newKey,
        value: newValue
      });
      setStatus('✅ Secret added successfully');
      setNewKey('');
      setNewValue('');
      fetchKeys();
    } catch (err) {
      setStatus(`❌ Error: ${err.response?.data?.detail || err.message}`);
    }
    setLoading(false);
  };

  return (
    <div className="glass-panel">
      <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <KeyRound size={20} color="var(--primary)" /> Security Vault
      </h3>
      <p style={{ color: 'var(--text-muted)', marginBottom: '16px' }}>
        Manage credentials for vault:// injections.
      </p>

      <form onSubmit={handleAdd} style={{ marginBottom: '24px' }}>
        <div className="grid-layout" style={{ padding: 0, gridTemplateColumns: '1fr 1fr' }}>
          <div className="form-group">
            <label>Secret Key (e.g., sauce_pass)</label>
            <input 
              value={newKey} 
              onChange={(e) => setNewKey(e.target.value)} 
              required 
              placeholder="Key Name"
            />
          </div>
          <div className="form-group">
            <label>Secret Value</label>
            <input 
              type="password"
              value={newValue} 
              onChange={(e) => setNewValue(e.target.value)} 
              required 
              placeholder="Value (Hidden)"
            />
          </div>
        </div>
        <button type="submit" disabled={loading} style={{ marginTop: '16px' }}>
          {loading ? 'Processing...' : <><Plus size={16} /> Add to Vault</>}
        </button>
        {status && <div className="status-message" style={{ marginTop: '12px' }}>{status}</div>}
      </form>

      <div style={{ marginTop: '24px' }}>
        <h4 style={{ marginBottom: '12px', fontSize: '1rem' }}>Stored Keys</h4>
        {keys.length === 0 ? (
          <div style={{ color: 'var(--text-muted)' }}>No secrets stored in the vault.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {keys.map((k) => (
              <div key={k} style={{ 
                background: 'rgba(255, 255, 255, 0.05)', 
                padding: '12px 16px', 
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                border: '1px solid rgba(255, 255, 255, 0.1)'
              }}>
                <Lock size={16} color="var(--text-muted)" />
                <span style={{ fontFamily: 'monospace', color: 'var(--primary)' }}>vault://{k}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
