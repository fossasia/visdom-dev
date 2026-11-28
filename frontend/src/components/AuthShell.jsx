/* Copyright 2017-present, The Visdom Authors */
import { Link, useLocation } from 'react-router-dom';

const LABEL = { display: 'block', fontSize: '13px', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '6px' };
const BUTTON = { width: '100%', height: '32px', backgroundColor: 'var(--pub-blue)', color: 'var(--pub-white)', borderColor: 'var(--pub-blue-deep)', marginTop: '6px' };
const NOTE = { textAlign: 'center', marginTop: '20px', fontSize: '13px', color: 'var(--text-muted)' };

export const AuthLabel = ({ children, htmlFor }) => (
  <label htmlFor={htmlFor} style={LABEL}>{children}</label>
);

export const AuthSubmit = ({ busy, busyText, children }) => (
  <button type="submit" disabled={busy} className="visdom-btn" style={BUTTON}>
    {busy ? busyText : children}
  </button>
);

export const AuthNote = ({ children }) => <div style={NOTE}>{children}</div>;

const LINK = { color: 'var(--pub-blue)', textDecoration: 'none', fontWeight: '600' };

export const AuthLink = ({ to, href, state, children }) =>
  href ? <a href={href} style={LINK}>{children}</a> : <Link to={to} state={state} style={LINK}>{children}</Link>;

export const AuthTextButton = ({ onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    style={{ ...LINK, background: 'none', border: 'none', padding: 0, font: 'inherit', fontWeight: '600', cursor: 'pointer' }}
  >
    {children}
  </button>
);

const FOOTER = { textAlign: 'center', marginTop: '16px', fontSize: '13px', color: 'var(--vc-text-muted)' };

const AuthShell = ({ subtitle, children }) => {
  const location = useLocation();
  const kept = { from: location.state?.from };

  return (
    <div className="auth-wrapper">
      <div className="visdom-panel auth-panel">
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <div className="visdom-logo" style={{ fontSize: '24px', margin: '0 0 4px 0', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'inherit', textDecoration: 'none' }}>
              <img src="/logo.svg" alt="Visdom Logo" style={{ height: '32px', width: '32px', borderRadius: '4px' }} />
              <span>visdom</span>
            </Link>
          </div>
          <h1 className="auth-title">{subtitle}</h1>
        </div>
        {children}
        <div style={FOOTER}>
          <AuthLink to={`/privacy${location.search}`} state={kept}>Privacy</AuthLink>
          {' · '}
          <AuthLink to={`/cookies${location.search}`} state={kept}>Cookies</AuthLink>
        </div>
      </div>
    </div>
  );
};

export default AuthShell;
