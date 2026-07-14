import React, { useState } from 'react';
import axios from 'axios';
import { User, Lock, Loader2 } from 'lucide-react';

const API_URL = "http://localhost:8000/api/v1";

export default function Auth({ onLogin }) {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    role: 'client'
  });
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setStatus('');
    
    try {
      if (isLogin) {
        const res = await axios.post(`${API_URL}/auth/login`, {
          username: formData.username,
          password: formData.password
        });
        localStorage.setItem('token', res.data.token);
        localStorage.setItem('role', res.data.role);
        localStorage.setItem('username', res.data.username);
        setStatus('✅ Success!');
        onLogin(res.data);
      } else {
        await axios.post(`${API_URL}/auth/signup`, formData);
        setStatus('✅ Account created! Please log in.');
        setIsLogin(true);
      }
    } catch (err) {
      setStatus(`❌ Error: ${err.response?.data?.detail || err.message}`);
    }
    setLoading(false);
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: 'var(--bg)' }}>
      <section className="glass-panel" style={{ width: '400px' }}>
        <h2 style={{ textAlign: 'center', marginBottom: '24px' }}>
          {isLogin ? 'Welcome Back' : 'Create Account'}
        </h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group" style={{ marginBottom: '16px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <User size={16} /> Username
            </label>
            <input 
              type="text" 
              value={formData.username} 
              onChange={e => setFormData({...formData, username: e.target.value})} 
              required
            />
          </div>
          
          <div className="form-group" style={{ marginBottom: '16px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Lock size={16} /> Password
            </label>
            <input 
              type="password" 
              value={formData.password} 
              onChange={e => setFormData({...formData, password: e.target.value})} 
              required
            />
          </div>

          {!isLogin && (
            <div className="form-group" style={{ marginBottom: '24px' }}>
              <label>Role</label>
              <select 
                value={formData.role} 
                onChange={e => setFormData({...formData, role: e.target.value})}
                style={{ width: '100%', padding: '12px', borderRadius: '8px', background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }}
              >
                <option value="client">Client (Execution)</option>
                <option value="admin">Admin (Monitoring)</option>
              </select>
            </div>
          )}
          
          <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
            {loading ? <Loader2 className="animate-spin" /> : (isLogin ? 'Log In' : 'Sign Up')}
          </button>
          
          <div style={{ textAlign: 'center', marginTop: '16px', fontSize: '0.9rem' }}>
            <span style={{ color: status.includes('❌') ? '#ef4444' : 'var(--accent)' }}>{status}</span>
          </div>

          <div style={{ textAlign: 'center', marginTop: '16px', fontSize: '0.9rem' }}>
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <span 
              style={{ color: 'var(--primary)', cursor: 'pointer', textDecoration: 'underline' }}
              onClick={() => { setIsLogin(!isLogin); setStatus(''); }}
            >
              {isLogin ? 'Sign up' : 'Log in'}
            </span>
          </div>
        </form>
      </section>
    </div>
  );
}
