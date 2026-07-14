import React, { useState } from 'react';
import axios from 'axios';
import { Play, Loader2 } from 'lucide-react';

const API_URL = "http://localhost:8000/api/v1";

export default function AgentRunner({ onExecute }) {
  const [formData, setFormData] = useState({
    session_id: 'ui_session_1',
    url: 'https://www.saucedemo.com',
    start_intent: 'login_action'
  });
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = async (e) => {
    const q = e.target.value;
    setSearchQuery(q);
    if (q.length < 2) {
      setSearchResults([]);
      return;
    }
    setIsSearching(true);
    const token = localStorage.getItem('token');
    try {
      const res = await axios.get(`${API_URL}/memory/search?query=${q}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSearchResults(res.data.data);
    } catch (err) {
      console.error("Search failed", err);
    }
    setIsSearching(false);
  };

  const selectSearchResult = (item) => {
    setFormData({ ...formData, url: `https://${item.domain}`, start_intent: item.intent });
    setSearchQuery('');
    setSearchResults([]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setStatus('Dispatching Auto-Pilot Extension...');
    
    // Dispatch event to the injected Content Script
    window.dispatchEvent(new CustomEvent("ANTIGRAVITY_START_AUTOPILOT", {
        detail: { intent: formData.start_intent }
    }));
    
    setStatus(`✅ Success! Auto-Pilot Agent Started in a new tab.`);
    if (onExecute) onExecute(formData.session_id);
    
    setTimeout(() => {
        setLoading(false);
    }, 1000);
  };

  return (
    <section className="glass-panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
          <Play size={24} color="var(--primary)" /> Execute Agent
        </h2>
        <div style={{ position: 'relative', width: '300px' }}>
          <input 
            type="text" 
            placeholder="🔍 Discover Workflows..." 
            value={searchQuery}
            onChange={handleSearch}
            style={{ width: '100%' }}
          />
          {searchResults.length > 0 && (
            <ul style={{
              position: 'absolute', top: '100%', left: 0, right: 0, 
              background: 'var(--surface)', border: '1px solid var(--border)', 
              borderRadius: '8px', zIndex: 10, padding: '8px', margin: 0, listStyle: 'none',
              maxHeight: '200px', overflowY: 'auto'
            }}>
              {searchResults.map((item, i) => (
                <li key={i} 
                  onClick={() => selectSearchResult(item)}
                  style={{ 
                    padding: '8px', cursor: 'pointer', borderBottom: '1px solid var(--border)',
                    display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem'
                  }}
                  onMouseOver={(e) => e.currentTarget.style.background = 'var(--bg)'}
                  onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <span style={{ fontWeight: 'bold' }}>{item.intent}</span>
                  <span style={{ color: 'var(--primary)' }}>[{item.tier}]</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="grid-layout" style={{ padding: '0', gridTemplateColumns: '1fr 1fr 1fr' }}>
          <div className="form-group">
            <label>Session ID</label>
            <input 
              value={formData.session_id} 
              onChange={e => setFormData({...formData, session_id: e.target.value})} 
              required
            />
          </div>
          <div className="form-group">
            <label>Target URL</label>
            <input 
              value={formData.url} 
              onChange={e => setFormData({...formData, url: e.target.value})} 
              required
            />
          </div>
          <div className="form-group">
            <label>Start Intent</label>
            <input 
              value={formData.start_intent} 
              onChange={e => setFormData({...formData, start_intent: e.target.value})} 
              required
            />
          </div>
        </div>
        
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
          <span style={{ fontSize: '0.9rem', color: status.includes('❌') ? '#ef4444' : 'var(--accent)' }}>
            {status}
          </span>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? <Loader2 className="animate-spin" /> : <Play size={18} />}
            Launch Auto-Pilot
          </button>
        </div>
      </form>
    </section>
  );
}
