/* Copyright 2017-present, The Visdom Authors */
import { Link } from 'react-router-dom';

const LABEL = { display: 'block', fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '6px' };
const BUTTON = { width: '100%', height: '32px', backgroundColor: '#3b5998', color: '#ffffff', borderColor: '#2f477a', marginTop: '6px' };
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

const LINK = { color: '#3b5998', textDecoration: 'none', fontWeight: '600' };

export const AuthLink = ({ to, href, children }) =>
  href ? <a href={href} style={LINK}>{children}</a> : <Link to={to} style={LINK}>{children}</Link>;

export const AuthTextButton = ({ onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    style={{ ...LINK, background: 'none', border: 'none', padding: 0, font: 'inherit', fontWeight: '600', cursor: 'pointer' }}
  >
    {children}
  </button>
);

const AuthShell = ({ subtitle, children }) => (
  <div className="auth-wrapper">
    <div className="visdom-panel auth-panel">
      <div style={{ textAlign: 'center', marginBottom: '24px' }}>
        <h2 className="visdom-logo" style={{ fontSize: '24px', margin: '0 0 4px 0', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          <img src="/logo.svg" alt="Visdom Logo" style={{ height: '32px', width: '32px', borderRadius: '4px' }} />
          <span>visdom</span>
        </h2>
        <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{subtitle}</div>
      </div>
      {children}
    </div>
  </div>
);

export default AuthShell;
