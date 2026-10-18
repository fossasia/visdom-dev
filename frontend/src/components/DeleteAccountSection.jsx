/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { api, useAuth } from '../context/AuthContext';
import { useConfirm } from '../context/ConfirmContext';
import { useToast } from './toast/useToast';
import { parseApiError } from '../utils/helpers';
import PasswordInput from './PasswordInput';

const formatDay = (value) =>
  new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });

const DeleteAccountSection = ({ onClose }) => {
  const { logout } = useAuth();
  const confirm = useConfirm();
  const toast = useToast();
  const [preview, setPreview] = useState(null);
  const [checking, setChecking] = useState(false);
  const [password, setPassword] = useState('');
  const [deleting, setDeleting] = useState(false);

  const handleStart = async () => {
    setChecking(true);
    try {
      const response = await api.get('/auth/me/deletion');
      setPreview(response.data);
    } catch (err) {
      toast.error(parseApiError(err, 'Could not check your account.'));
    } finally {
      setChecking(false);
    }
  };

  const handleDelete = async (e) => {
    e.preventDefault();
    const ok = await confirm({
      title: 'Delete account',
      message: `You will be signed out everywhere and your API keys will stop working. Your account is removed for good after ${preview.grace_days} days unless you sign in before then.`,
      confirmText: 'Delete my account',
      danger: true,
    });
    if (!ok) return;

    setDeleting(true);
    try {
      const response = await api.post('/auth/me/deletion', { password });
      toast.success(
        `Your account will be deleted on ${formatDay(response.data.delete_after)}. Sign in before then to keep it.`,
        { duration: 12000 }
      );
      onClose();
      await logout();
    } catch (err) {
      toast.error(parseApiError(err, 'Could not delete the account.'));
      setDeleting(false);
    }
  };

  return (
    <div className="gc-password-form">
      <label className="gc-label gc-mb-1 gc-text-danger">Delete account</label>

      {!preview && (
        <>
          <div className="gc-text-desc-muted gc-mb-1">
            Your account stops working straight away and is removed for good after 30 days. Signing in
            before then cancels it.
          </div>
          <button className="gc-btn gc-btn-danger gc-w-full" onClick={handleStart} disabled={checking} type="button">
            <Trash2 size={13} />
            {checking ? 'Checking...' : 'Delete Account'}
          </button>
        </>
      )}

      {preview && preview.blockers.length > 0 && (
        <>
          <div className="gc-text-desc-muted gc-mb-1">
            Other people still use these workspaces. Put someone else in charge of each one first:
          </div>
          <ul className="gc-delete-list">
            {preview.blockers.map((ws) => (
              <li key={ws.id}>
                <strong>{ws.name}</strong>: {ws.reason}
              </li>
            ))}
          </ul>
        </>
      )}

      {preview && preview.blockers.length === 0 && (
        <form onSubmit={handleDelete}>
          <div className="gc-text-desc-muted gc-mb-1">
            Your account stops working straight away and is removed for good after {preview.grace_days} days.
            Signing in before then cancels it.
          </div>
          {preview.leaving_with.length > 0 && (
            <>
              <div className="gc-text-desc-muted gc-mb-1">
                Nobody else uses these workspaces, so they are deleted with it:
              </div>
              <ul className="gc-delete-list">
                {preview.leaving_with.map((ws) => (
                  <li key={ws.id}>
                    <strong>{ws.name}</strong>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="gc-field">
            <PasswordInput
              className="gc-input"
              required
              autoComplete="current-password"
              placeholder="Your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button type="submit" className="gc-btn gc-btn-danger gc-w-full" disabled={deleting || !password}>
            {deleting ? 'Deleting...' : 'Delete My Account'}
          </button>
        </form>
      )}
    </div>
  );
};

export default DeleteAccountSection;
