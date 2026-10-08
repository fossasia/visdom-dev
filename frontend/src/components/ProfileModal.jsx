/* Copyright 2017-present, The Visdom Authors */
import { useEffect, useState } from 'react';
import { Check, X } from 'lucide-react';
import { api, useAuth } from '../context/AuthContext';
import { useToast } from './toast/useToast';
import { parseApiError } from '../utils/helpers';
import ModalPortal from './ModalPortal';
import PasswordInput from './PasswordInput';
import { formatJoined, formatLastSignIn, planName } from '../utils/profileDetails';

const USERNAME_PATTERN = /^[A-Za-z0-9_-]{3,30}$/;
const MIN_PASSWORD = 6;

const ProfileModal = ({ onClose }) => {
  const { user, setUser, setAccessToken } = useAuth();
  const [username, setUsername] = useState(user?.username || '');
  const [usernameAvailable, setUsernameAvailable] = useState(null);
  const [checkingUsername, setCheckingUsername] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changing, setChanging] = useState(false);
  const toast = useToast();

  const isUnchanged = username === user?.username;

  const joined = formatJoined(user?.created_at);
  const lastSignIn = formatLastSignIn(user?.last_login_at);

  useEffect(() => {
    if (isUnchanged || !username) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setUsernameAvailable(null);
      return;
    }

    if (!USERNAME_PATTERN.test(username)) {
      setUsernameAvailable(false);
      return;
    }

    setCheckingUsername(true);
    const timeout = setTimeout(async () => {
      try {
        const response = await api.get('/auth/username-availability', { params: { username } });
        setUsernameAvailable(response.data.available);
      } catch (err) { // eslint-disable-line no-unused-vars
        setUsernameAvailable(null);
      } finally {
        setCheckingUsername(false);
      }
    }, 400);

    return () => clearTimeout(timeout);
  }, [username, isUnchanged]);

  const canSubmit = !isUnchanged && USERNAME_PATTERN.test(username) && usernameAvailable === true;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError('');
    try {
      const response = await api.patch('/auth/me/username', { username });
      setUser(response.data);
      toast.success('Username updated.');
      onClose();
    } catch (err) {
      setError(parseApiError(err, 'Failed to update username.'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (newPassword.length < MIN_PASSWORD) {
      toast.error(`Password should have at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error('Passwords do not match.');
      return;
    }

    setChanging(true);
    try {
      const response = await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setAccessToken(response.data.access_token);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      toast.success('Password changed. Other devices have been signed out.');
    } catch (err) {
      toast.error(parseApiError(err, 'Could not change the password.'));
    } finally {
      setChanging(false);
    }
  };

  return (
    <ModalPortal onClose={onClose}>
      <div className="gc-modal-header">
        <span className="gc-modal-title">Profile</span>
        <button className="gc-modal-close" onClick={onClose} type="button">
          <X size={16} />
        </button>
      </div>

      {error && <div className="gc-form-error">{error}</div>}

      <div className="gc-field">
        <label className="gc-label gc-mb-1">Email Address</label>
        <div className="gc-settings-value">{user?.email}</div>
      </div>

      <div className="gc-field">
        <label className="gc-label gc-mb-1">Plan</label>
        <div className="gc-settings-value">{planName(user?.tier)}</div>
      </div>

      {joined && (
        <div className="gc-field">
          <label className="gc-label gc-mb-1">Member since</label>
          <div className="gc-settings-value">{joined}</div>
        </div>
      )}

      {lastSignIn && (
        <div className="gc-field">
          <label className="gc-label gc-mb-1">Last sign-in</label>
          <div className="gc-settings-value">{lastSignIn}</div>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="gc-field">
          <label className="gc-label">Username</label>
          <input
            type="text"
            className="gc-input"
            value={username}
            onChange={(e) => setUsername(e.target.value.trim())}
            autoComplete="off"
            spellCheck={false}
          />
          {!isUnchanged && username && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '6px', fontSize: '12px' }}>
              {!USERNAME_PATTERN.test(username) ? (
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
        </div>

        <button
          type="submit"
          disabled={!canSubmit || submitting}
          className="gc-btn gc-btn-primary gc-w-full gc-mt-1"
        >
          {submitting ? 'Saving...' : 'Save Username'}
        </button>
      </form>

      <form onSubmit={handleChangePassword} className="gc-password-form">
        <div className="gc-field">
          <label className="gc-label gc-mb-1">Change password</label>
          <PasswordInput
            className="gc-input"
            required
            autoComplete="current-password"
            placeholder="Current password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </div>
        <div className="gc-field">
          <PasswordInput
            className="gc-input"
            required
            autoComplete="new-password"
            placeholder={`New password, at least ${MIN_PASSWORD} characters`}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </div>
        <div className="gc-field">
          <PasswordInput
            className="gc-input"
            required
            autoComplete="new-password"
            placeholder="Re-enter new password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={changing || !currentPassword || !newPassword}
          className="gc-btn gc-w-full"
        >
          {changing ? 'Changing...' : 'Change Password'}
        </button>
        <div className="gc-text-desc-muted gc-mt-1">
          Changing it signs you out on every other device.
        </div>
      </form>
    </ModalPortal>
  );
};

export default ProfileModal;
