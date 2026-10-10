/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../context/AuthContext';
import AuthShell, { AuthLink, AuthLabel, AuthNote, AuthSubmit } from '../components/AuthShell';
import PasswordInput from '../components/PasswordInput';
import { useToast } from '../components/toast/useToast';
import { apiErrorText, tokenFromHash } from '../utils/authLinks';

const MIN_LENGTH = 6;

const ResetPassword = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const [token] = useState(() => tokenFromHash(location.hash));
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [refused, setRefused] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password.length < MIN_LENGTH) {
      toast.error(`Password should have at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (password !== confirmPassword) {
      toast.error('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post('/auth/reset-password', { token, password });
      toast.success(data.detail || 'Your password has been changed.');
      navigate('/login', { replace: true });
    } catch (err) {
      if (err?.response?.status === 400) setRefused(true);
      toast.error(apiErrorText(err, 'Could not change the password. Try again in a moment.'));
    } finally {
      setSubmitting(false);
    }
  };

  if (!token || refused) {
    return (
      <AuthShell subtitle="Reset your password">
        <p style={{ fontSize: '13px', lineHeight: 1.5, color: 'var(--text-secondary)', margin: 0 }}>
          This reset link is invalid or has expired. Links work once, for an hour after they are sent.
        </p>
        <AuthNote>
          <AuthLink to="/forgot-password">Ask for a new link</AuthLink>
        </AuthNote>
      </AuthShell>
    );
  }

  return (
    <AuthShell subtitle="Choose a new password">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div>
          <AuthLabel htmlFor="reset-password">New Password</AuthLabel>
          <PasswordInput
            id="reset-password"
            required
            autoFocus
            autoComplete="new-password"
            placeholder={`Minimum ${MIN_LENGTH} characters`}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div>
          <AuthLabel htmlFor="reset-confirm">Confirm Password</AuthLabel>
          <PasswordInput
            id="reset-confirm"
            required
            autoComplete="new-password"
            placeholder="Re-enter password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </div>
        <AuthSubmit busy={submitting} busyText="Saving...">Set new password</AuthSubmit>
      </form>
      <AuthNote>
        This also signs you out on every device.{' '}
        <AuthLink to="/login">Back to sign in</AuthLink>
      </AuthNote>
    </AuthShell>
  );
};

export default ResetPassword;
