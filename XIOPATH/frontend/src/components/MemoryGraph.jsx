import React, { useState } from 'react';
import axios from 'axios';
import { Network, Search, Loader2, Link, Zap } from 'lucide-react';

const API_URL = "http://localhost:8000/api/v1";

const GraphNode = ({ node }) => {
  if (!node) return null;
  return (
    <div style={{
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: '8px',
      padding: '16px',
      marginBottom: '12px',
      position: 'relative'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ color: 'var(--secondary)', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
          <Network size={16} /> {node.intent}
        </h4>
        <span style={{ 
          fontSize: '0.75rem', 
          background: 'rgba(0,0,0,0.3)', 
          padding: '4px 8px', 
          borderRadius: '4px' 
        }}>
          {node.tier}
        </span>
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px', fontSize: '0.85rem' }}>
        <div><strong>Action:</strong> {node.action_type}</div>
        <div><strong>Domain:</strong> {node.domain}</div>
        {node.volatility_type !== 'static' && (
          <div style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Zap size={14} /> <strong>Volatility:</strong> {node.volatility_type}
          </div>
        )}
      </div>

      {node.next_nodes && node.next_nodes.length > 0 && (
        <div style={{ marginTop: '16px', paddingLeft: '16px', borderLeft: '2px dashed rgba(255,255,255,0.1)' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Link size={12} /> NEXT INTENTS
          </div>
          {node.next_nodes.map((nextNode, i) => (
            <GraphNode key={i} node={nextNode} />
          ))}
        </div>
      )}
    </div>
  );
};

export default function MemoryGraph() {
  const [url, setUrl] = useState('https://www.saucedemo.com');
  const [intent, setIntent] = useState('login_action');
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchGraph = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setGraphData(null);

    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API_URL}/memory/graph`, {
        params: { url, intent: intent },
        headers: { Authorization: `Bearer ${token}` }
      });
      setGraphData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Graph not found for this intent.');
    }
    setLoading(false);
  };

  return (
    <section className="glass-panel" style={{ height: '100%' }}>
      <h2 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Network size={24} color="var(--secondary)" /> Memory Graph
      </h2>
      
      <form onSubmit={fetchGraph} style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
        <input 
          placeholder="Domain URL" 
          value={url} 
          onChange={e => setUrl(e.target.value)} 
          style={{ flex: 1 }}
        />
        <input 
          placeholder="Intent Name" 
          value={intent} 
          onChange={e => setIntent(e.target.value)} 
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn-secondary" disabled={loading}>
          {loading ? <Loader2 className="animate-spin" /> : <Search size={18} />}
        </button>
      </form>

      {error && <div style={{ color: '#ef4444', marginBottom: '16px' }}>{error}</div>}

      {graphData && (
        <div style={{ 
          background: 'rgba(0,0,0,0.3)', 
          padding: '24px', 
          borderRadius: '8px',
          maxHeight: '400px',
          overflowY: 'auto'
        }}>
          <GraphNode node={graphData} />
        </div>
      )}
      
      {!graphData && !error && !loading && (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px 0' }}>
          Enter a URL and Intent to visualize the workflow.
        </div>
      )}
    </section>
  );
}
