import React, { useState } from 'react';
import axios from 'axios';
import { ShieldCheck, Loader2 } from 'lucide-react';

const API_URL = "http://localhost:8000/api/v1";

export default function ConsensusTool() {
  const [domain, setDomain] = useState('saucedemo.com');
  const [nodeId, setNodeId] = useState('login_action');
  const [clientId, setClientId] = useState('client_A');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);

  const handlePromote = async (e) => {
    e.preventDefault();
    setLoading(true);
    setStatus('Submitting vote...');
    
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API_URL}/memory/promote`, {
        domain: domain,
        node_id: nodeId,
        client_id: clientId,
        action_data: { 
          "intent": nodeId, 
          "domain": domain,
          "visibility": "visible",
          "face_value": "mock",
          "action_type": "click",
          "action_params": {},
          "device_type": "desktop",
          "os_name": "macintel",
          "browser": "chromium",
          "viewport_width": 1280,
          "viewport_height": 800
        }
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setStatus(`✅ Success! Node is now: ${res.data.current_tier}`);
    } catch (err) {
      let errMsg = err.message;
      if (err.response?.data?.detail) {
        errMsg = Array.isArray(err.response.data.detail) 
          ? err.response.data.detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(' | ') 
          : err.response.data.detail;
      }
      setStatus(`❌ Error: ${errMsg}`);
    }
    setLoading(false);
  };

  return (
    <section className="glass-panel" style={{ height: '100%' }}>
      <h2 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <ShieldCheck size={24} color="var(--accent)" /> Global Consensus
      </h2>
      
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '16px' }}>
        Simulate a client executing a node to build Server Consensus (3 unique clients required for Global Primary).
      </p>

      <form onSubmit={handlePromote}>
        <div className="form-group">
          <label>Domain</label>
          <input 
            value={domain} 
            onChange={e => setDomain(e.target.value)} 
            required
          />
        </div>
        <div className="form-group">
          <label>Memory Node ID (Intent)</label>
          <input 
            value={nodeId} 
            onChange={e => setNodeId(e.target.value)} 
            required
          />
        </div>
        <div className="form-group">
          <label>Simulated Client ID</label>
          <input 
            value={clientId} 
            onChange={e => setClientId(e.target.value)} 
            required
          />
        </div>
        
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
          <span style={{ fontSize: '0.9rem', color: status.includes('❌') ? '#ef4444' : 'var(--accent)' }}>
            {status}
          </span>
          <button type="submit" className="btn-secondary" disabled={loading} style={{ color: 'var(--accent)', borderColor: 'var(--accent)' }}>
            {loading ? <Loader2 className="animate-spin" /> : <ShieldCheck size={18} />}
            Submit Vote
          </button>
        </div>
      </form>
    </section>
  );
}
