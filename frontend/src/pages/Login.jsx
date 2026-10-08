/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import PasswordInput from '../components/PasswordInput';
import { resolvePostAuthTarget, redirectAfterAuth } from '../utils/helpers';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = resolvePostAuthTarget(location);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    
    try {
      await login(email, password);
      redirectAfterAuth(from, navigate);
    } catch (err) {
      const detail = err.response?.data?.detail;
      let errorMsg = 'Login failed. Please check your credentials.';
      if (typeof detail === 'string') {
        errorMsg = detail;
      } else if (Array.isArray(detail)) {
        errorMsg = detail.map(d => {
          if (d.msg === 'String should have at least 6 characters') {
            return 'Password should have atleast 6 characters';
          }
          return d.msg;
        }).join(', ');
      }
      setError(errorMsg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="visdom-panel auth-panel">
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <h2 className="visdom-logo" style={{ fontSize: '24px', margin: '0 0 4px 0', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            <img src="/logo.svg" alt="Visdom Logo" style={{ height: '32px', width: '32px', borderRadius: '4px' }} />
            <span>visdom</span>
          </h2>
          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Sign in to manage your workspaces</div>
        </div>

        {error && (
          <div style={{
            background: 'rgba(217, 83, 79, 0.1)',
            border: '1px solid var(--danger-bg)',
            borderRadius: '2px',
            padding: '10px',
            color: 'var(--danger-bg)',
            fontSize: '13px',
            marginBottom: '16px'
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Email Address
            </label>
            <input
              type="email"
              required
              className="visdom-input"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '6px' }}>
              <label style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)' }}>
                Password
              </label>
              <Link to="/forgot-password" state={{ email }} style={{ fontSize: '12px', color: '#3b5998', textDecoration: 'none' }}>
                Forgot password?
              </Link>
            </div>
            <PasswordInput
              required
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button type="submit" disabled={submitting} className="visdom-btn" style={{
            width: '100%',
            height: '32px',
            backgroundColor: '#3b5998',
            color: '#ffffff',
            borderColor: '#2f477a',
            marginTop: '6px'
          }}>
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '13px', color: 'var(--text-muted)' }}>
          Don't have an account?{' '}
          <Link to={`/register${location.search}`} state={{ from: location.state?.from }} style={{ color: '#3b5998', textDecoration: 'none', fontWeight: '600' }}>
            Sign up
          </Link>
        </div>
      </div>
    </div>
  );
};

export default Login;
