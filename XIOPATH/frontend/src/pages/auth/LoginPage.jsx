/**
 * XIOPATH — Login Page
 * ======================
 * Enterprise-grade login with branded illustration panel,
 * animated gradient background, and server connection indicator.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, Lock, Loader2, Eye, EyeOff, AlertCircle, ArrowRight } from 'lucide-react';
import useAuthStore from '../../stores/authStore';

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { login, signup } = useAuthStore();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      if (isLogin) {
        const user = await login(username, password);
        navigate(user.role === 'admin' ? '/admin' : '/dashboard');
      } else {
        await signup(username, password);
        setSuccess('Account created successfully. Please log in.');
        setIsLogin(true);
        setPassword('');
      }
    } catch (err) {
      setError(err.message || 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      minHeight: '100vh',
      background: 'var(--xp-bg-void)',
      overflow: 'hidden',
    }}>
      {/* ─── Left Panel: Brand ────────────────────── */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 'var(--xp-space-12)',
        position: 'relative',
        overflow: 'hidden',
      }}>
        {/* Ambient gradient orbs */}
        <div style={{
          position: 'absolute',
          width: '500px',
          height: '500px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(6, 214, 160, 0.12), transparent 70%)',
          top: '10%',
          left: '-10%',
          animation: 'xp-float 6s ease-in-out infinite',
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute',
          width: '400px',
          height: '400px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(124, 58, 237, 0.10), transparent 70%)',
          bottom: '5%',
          right: '-5%',
          animation: 'xp-float 8s ease-in-out infinite reverse',
          pointerEvents: 'none',
        }} />

        {/* Brand content */}
        <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', maxWidth: '460px' }}
             className="xp-animate-fade-in">
          {/* Logo */}
          <div style={{
            width: 72,
            height: 72,
            borderRadius: 'var(--xp-radius-xl)',
            background: 'var(--xp-gradient-brand)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto var(--xp-space-6)',
            boxShadow: '0 8px 32px rgba(6, 214, 160, 0.2)',
          }}>
            <span style={{
              fontFamily: 'var(--xp-font-display)',
              fontSize: 'var(--xp-text-3xl)',
              fontWeight: 'var(--xp-weight-bold)',
              color: 'var(--xp-text-inverse)',
            }}>X</span>
          </div>

          <h1 style={{
            fontFamily: 'var(--xp-font-display)',
            fontSize: '2.5rem',
            fontWeight: 'var(--xp-weight-bold)',
            letterSpacing: 'var(--xp-tracking-wide)',
            marginBottom: 'var(--xp-space-3)',
          }}>
            <span className="xp-gradient-text">XIOPATH</span>
          </h1>

          <p style={{
            fontSize: 'var(--xp-text-lg)',
            color: 'var(--xp-text-secondary)',
            lineHeight: 'var(--xp-leading-relaxed)',
            marginBottom: 'var(--xp-space-8)',
          }}>
            Autonomous Browser Intelligence Platform
          </p>

          {/* Feature pills */}
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 'var(--xp-space-2)',
            justifyContent: 'center',
          }}>
            {['Self-Learning Memory', 'Zero-Shot Inference', 'Autonomous Agents', 'Multi-Node Swarm'].map((feat) => (
              <span key={feat} style={{
                padding: '6px 14px',
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid var(--xp-border-subtle)',
                borderRadius: 'var(--xp-radius-full)',
                fontSize: 'var(--xp-text-xs)',
                color: 'var(--xp-text-muted)',
                fontWeight: 'var(--xp-weight-medium)',
              }}>
                {feat}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Right Panel: Form ────────────────────── */}
      <div style={{
        width: '480px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: 'var(--xp-space-12)',
        background: 'var(--xp-bg-base)',
        borderLeft: '1px solid var(--xp-border-subtle)',
      }}>
        <div className="xp-animate-slide-up" style={{ maxWidth: '360px', width: '100%', margin: '0 auto' }}>
          <h2 style={{
            fontFamily: 'var(--xp-font-display)',
            fontSize: 'var(--xp-text-2xl)',
            marginBottom: 'var(--xp-space-1)',
          }}>
            {isLogin ? 'Welcome back' : 'Create account'}
          </h2>
          <p style={{
            fontSize: 'var(--xp-text-sm)',
            color: 'var(--xp-text-muted)',
            marginBottom: 'var(--xp-space-8)',
          }}>
            {isLogin
              ? 'Sign in to your XIOPATH workspace'
              : 'Set up your XIOPATH credentials'
            }
          </p>

          {/* Error / Success messages */}
          {error && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--xp-space-2)',
              padding: 'var(--xp-space-3)',
              background: 'var(--xp-danger-bg)',
              border: '1px solid rgba(239, 68, 68, 0.2)',
              borderRadius: 'var(--xp-radius-md)',
              marginBottom: 'var(--xp-space-4)',
              fontSize: 'var(--xp-text-sm)',
              color: 'var(--xp-danger)',
            }} className="xp-animate-slide-up">
              <AlertCircle size={16} />
              {error}
            </div>
          )}
          {success && (
            <div style={{
              padding: 'var(--xp-space-3)',
              background: 'var(--xp-success-bg)',
              border: '1px solid rgba(6, 214, 160, 0.2)',
              borderRadius: 'var(--xp-radius-md)',
              marginBottom: 'var(--xp-space-4)',
              fontSize: 'var(--xp-text-sm)',
              color: 'var(--xp-success)',
            }} className="xp-animate-slide-up">
              {success}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {/* Username */}
            <div className="xp-field" style={{ marginBottom: 'var(--xp-space-4)' }}>
              <label className="xp-label" htmlFor="login-username">
                <User size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
                Username
              </label>
              <input
                id="login-username"
                className="xp-input"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                required
                autoComplete="username"
                autoFocus
              />
            </div>

            {/* Password */}
            <div className="xp-field" style={{ marginBottom: 'var(--xp-space-4)' }}>
              <label className="xp-label" htmlFor="login-password">
                <Lock size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
                Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="login-password"
                  className="xp-input"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                  autoComplete={isLogin ? 'current-password' : 'new-password'}
                  style={{ paddingRight: '40px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    color: 'var(--xp-text-muted)',
                    cursor: 'pointer',
                    padding: '4px',
                    display: 'flex',
                  }}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              className="xp-btn xp-btn-primary xp-btn-lg"
              disabled={loading}
              style={{ width: '100%', marginTop: 'var(--xp-space-2)' }}
            >
              {loading ? (
                <Loader2 size={18} className="xp-animate-spin" />
              ) : (
                <>
                  {isLogin ? 'Sign In' : 'Create Account'}
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          {/* Toggle login/signup */}
          <div style={{
            textAlign: 'center',
            marginTop: 'var(--xp-space-6)',
            fontSize: 'var(--xp-text-sm)',
            color: 'var(--xp-text-muted)',
          }}>
            {isLogin ? "Don't have an account? " : 'Already have an account? '}
            <button
              type="button"
              onClick={() => { setIsLogin(!isLogin); setError(''); setSuccess(''); }}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--xp-cyan)',
                cursor: 'pointer',
                fontFamily: 'var(--xp-font-body)',
                fontSize: 'var(--xp-text-sm)',
                fontWeight: 'var(--xp-weight-medium)',
                textDecoration: 'underline',
                textUnderlineOffset: '2px',
              }}
            >
              {isLogin ? 'Create one' : 'Sign in'}
            </button>
          </div>

          {/* Version */}
          <div style={{
            textAlign: 'center',
            marginTop: 'var(--xp-space-10)',
            fontSize: 'var(--xp-text-xs)',
            color: 'var(--xp-text-disabled)',
          }}>
            XIOPATH v2.0 — Autonomous Browser Intelligence
          </div>
        </div>
      </div>
    </div>
  );
}
