/* Copyright 2017-present, The Visdom Authors */
import { useEffect, useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Check, RefreshCw, X } from 'lucide-react';
import { useAuth, api } from '../context/AuthContext';
import PasswordInput from '../components/PasswordInput';
import { resolvePostAuthTarget, redirectAfterAuth } from '../utils/helpers';

const USERNAME_PATTERN = /^[A-Za-z0-9_-]{3,30}$/;

const Register = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [usernameMode, setUsernameMode] = useState('auto'); // 'auto' | 'custom'
  const [autoUsername, setAutoUsername] = useState('');
  const [autoUsernameLoading, setAutoUsernameLoading] = useState(true);
  const [customUsername, setCustomUsername] = useState('');
  const [usernameAvailable, setUsernameAvailable] = useState(null); // null | true | false
  const [checkingUsername, setCheckingUsername] = useState(false);

  const { register, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = resolvePostAuthTarget(location);

  const fetchSuggestion = async (seed) => {
    setAutoUsernameLoading(true);
    try {
      const response = await api.get('/auth/generate-username', { params: seed ? { seed } : {} });
      setAutoUsername(response.data.username);
    } catch (err) {  
      console.error('Error generating username suggestion', err);
    } finally {
      setAutoUsernameLoading(false);
    }
  };

  useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
fetchSuggestion();
  }, []);

  useEffect(() => {
    if (usernameMode !== 'custom' || !customUsername) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setUsernameAvailable(null);
      return;
    }

    if (!USERNAME_PATTERN.test(customUsername)) {
      setUsernameAvailable(false);
      return;
    }

    setCheckingUsername(true);
    const timeout = setTimeout(async () => {
      try {
        const response = await api.get('/auth/username-availability', { params: { username: customUsername } });
        setUsernameAvailable(response.data.available);
      } catch (err) { // eslint-disable-line no-unused-vars
        setUsernameAvailable(null);
      } finally {
        setCheckingUsername(false);
      }
    }, 400);

    return () => clearTimeout(timeout);
  }, [customUsername, usernameMode]);

  const handleEmailBlur = () => {
    if (usernameMode === 'auto' && email.includes('@')) {
      fetchSuggestion(email.split('@')[0]);
    }
  };

  const usernameIsValidCustom = usernameMode === 'custom' && USERNAME_PATTERN.test(customUsername) && usernameAvailable === true;
  const usernameReady = usernameMode === 'auto' ? Boolean(autoUsername) && !autoUsernameLoading : usernameIsValidCustom;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    if (!usernameReady) {
      setError('Please choose a valid, available username.');
      return;
    }

    const finalUsername = usernameMode === 'auto' ? autoUsername : customUsername;

    setSubmitting(true);
    try {
      await register(email, password, finalUsername);
      setSuccess('Account created! Logging you in...');
      await login(email, password);
      redirectAfterAuth(from, navigate);
    } catch (err) {  
      const detail = err.response?.data?.detail;
      let errorMsg = 'Registration failed. Please try again.';
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
          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Create your user account</div>
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

        {success && (
          <div style={{
            background: 'rgba(92, 184, 92, 0.1)',
            border: '1px solid var(--success-bg)',
            borderRadius: '2px',
            padding: '10px',
            color: 'var(--success-bg)',
            fontSize: '13px',
            marginBottom: '16px'
          }}>
            {success}
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
              onBlur={handleEmailBlur}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Username
            </label>

            <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
              <button
                type="button"
                onClick={() => setUsernameMode('auto')}
                className="visdom-btn"
                style={{
                  flex: 1,
                  backgroundColor: usernameMode === 'auto' ? '#3b5998' : undefined,
                  color: usernameMode === 'auto' ? '#ffffff' : undefined,
                  borderColor: usernameMode === 'auto' ? '#2f477a' : undefined,
                }}
              >
                Auto-generate
              </button>
              <button
                type="button"
                onClick={() => setUsernameMode('custom')}
                className="visdom-btn"
                style={{
                  flex: 1,
                  backgroundColor: usernameMode === 'custom' ? '#3b5998' : undefined,
                  color: usernameMode === 'custom' ? '#ffffff' : undefined,
                  borderColor: usernameMode === 'custom' ? '#2f477a' : undefined,
                }}
              >
                Choose my own
              </button>
            </div>

            {usernameMode === 'auto' ? (
              <div style={{ display: 'flex', gap: '8px' }}>
                <div
                  className="visdom-input"
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    fontFamily: 'monospace',
                    color: 'var(--text-primary)',
                    background: '#f5f5f5',
                  }}
                >
                  {autoUsernameLoading ? 'Generating...' : autoUsername}
                </div>
                <button
                  type="button"
                  onClick={() => fetchSuggestion(email.includes('@') ? email.split('@')[0] : undefined)}
                  className="visdom-btn"
                  title="Generate a different username"
                  style={{ width: '36px', padding: 0 }}
                >
                  <RefreshCw size={14} />
                </button>
              </div>
            ) : (
              <>
                <input
                  type="text"
                  className="visdom-input"
                  placeholder="your_username"
                  value={customUsername}
                  onChange={(e) => setCustomUsername(e.target.value.trimStart())}
                  autoComplete="off"
                  spellCheck={false}
                />
                {customUsername && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '6px', fontSize: '12px' }}>
                    {!USERNAME_PATTERN.test(customUsername) ? (
                      <span style={{ color: 'var(--danger-bg)' }}>
                        3-30 characters: letters, numbers, underscores, hyphens.
                      </span>
                    ) : checkingUsername ? (
                      <span style={{ color: 'var(--text-muted)' }}>Checking availability...</span>
                    ) : usernameAvailable ? (
                      <span style={{ color: 'var(--success-bg)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Check size={12} /> Available
                      </span>
                    ) : (
                      <span style={{ color: 'var(--danger-bg)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <X size={12} /> Already taken
                      </span>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Password
            </label>
            <PasswordInput
              required
              autoComplete="new-password"
              placeholder="Minimum 6 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Confirm Password
            </label>
            <PasswordInput
              required
              autoComplete="new-password"
              placeholder="Re-enter password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>

          <button type="submit" disabled={submitting || !usernameReady} className="visdom-btn" style={{
            width: '100%',
            height: '32px',
            backgroundColor: '#3b5998',
            color: '#ffffff',
            borderColor: '#2f477a',
            marginTop: '6px'
          }}>
            {submitting ? 'Creating account...' : 'Create Account'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '13px', color: 'var(--text-muted)' }}>
          Already have an account?{' '}
          <Link to={`/login${location.search}`} state={{ from: location.state?.from }} style={{ color: '#3b5998', textDecoration: 'none', fontWeight: '600' }}>
            Sign in
          </Link>
        </div>

        <div style={{ textAlign: 'center', marginTop: '16px', fontSize: '12px', color: 'var(--text-muted)' }}>
          <Link to="/privacy" style={{ color: 'var(--text-muted)' }}>Privacy</Link>
          {' · '}
          <Link to="/cookies" style={{ color: 'var(--text-muted)' }}>Cookies</Link>
        </div>
      </div>
    </div>
  );
};

export default Register;
