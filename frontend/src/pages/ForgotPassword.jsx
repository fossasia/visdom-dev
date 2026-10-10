/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from '../context/AuthContext';
import AuthShell, { AuthLink, AuthLabel, AuthNote, AuthSubmit, AuthTextButton } from '../components/AuthShell';
import { useToast } from '../components/toast/useToast';
import { apiErrorText } from '../utils/authLinks';
import { supportHref } from '../utils/supportContact';

const MESSAGE = { fontSize: '13px', lineHeight: 1.5, color: 'var(--text-secondary)', margin: 0 };

const ForgotPassword = () => {
  const location = useLocation();
  const toast = useToast();
  const [email, setEmail] = useState(location.state?.email || '');
  const [submitting, setSubmitting] = useState(false);
  const [outcome, setOutcome] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { data } = await api.post('/auth/forgot-password', { email: email.trim() });
      setOutcome(data);
    } catch (err) {
      toast.error(apiErrorText(err, 'Could not send a reset link. Try again in a moment.'));
    } finally {
      setSubmitting(false);
    }
  };

  const backToSignIn = (
    <AuthNote>
      Remembered it?{' '}
      <AuthLink to="/login">Sign in</AuthLink>
    </AuthNote>
  );

  if (outcome && !outcome.email_enabled) {
    const help = supportHref(outcome.support_contact, 'Password reset');
    return (
      <AuthShell subtitle="Reset your password">
        <p style={MESSAGE}>
          This server cannot send email yet, so a reset link cannot be sent.{' '}
          {help ? (
            <AuthLink href={help}>Contact support</AuthLink>
          ) : (
            'Ask whoever runs this server'
          )}{' '}
          to get back into your account.
        </p>
        {backToSignIn}
      </AuthShell>
    );
  }

  if (outcome) {
    return (
      <AuthShell subtitle="Check your inbox">
        <p style={MESSAGE}>
          If <strong>{email.trim()}</strong> has an account, a link to choose a new password is on its way.
          It works once, for the next hour.
        </p>
        <AuthNote>
          Nothing arrived?{' '}
          <AuthTextButton onClick={() => setOutcome(null)}>Send another</AuthTextButton>
        </AuthNote>
        {backToSignIn}
      </AuthShell>
    );
  }

  return (
    <AuthShell subtitle="Reset your password">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <p style={MESSAGE}>Enter the email you signed up with and we will send you a link to choose a new password.</p>
        <div>
          <AuthLabel htmlFor="forgot-email">Email Address</AuthLabel>
          <input
            id="forgot-email"
            type="email"
            required
            autoFocus
            className="visdom-input"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <AuthSubmit busy={submitting} busyText="Sending...">Send reset link</AuthSubmit>
      </form>
      {backToSignIn}
    </AuthShell>
  );
};

export default ForgotPassword;
