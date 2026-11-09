/* Copyright 2017-present, The Visdom Authors */
import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, Link2, Lock, Trash2 } from 'lucide-react';
import { api } from '../../context/AuthContext';
import { useConfirm } from '../../context/ConfirmContext';
import { useToast } from '../toast/useToast';
import { copyToClipboard } from '../../utils/clipboard';
import { cachedGet, invalidate } from '../../utils/requestCache';
import { EXPIRY_PRESETS, ROLE_BADGE, parseApiError, resolveExpiresAt } from '../../utils/helpers';

const shareUrl = (linkId) => `${window.location.origin}/share/${linkId}`;

const SharedLinksTab = ({ workspaceId, isAdmin }) => {
  const confirm = useConfirm();
  const toast = useToast();
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [role, setRole] = useState('member');
  const [expiryPreset, setExpiryPreset] = useState('none');
  const [customExpiresAt, setCustomExpiresAt] = useState('');
  const [password, setPassword] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [copiedId, setCopiedId] = useState(null);

  const fetchLinks = useCallback(async () => {
    const key = `/workspaces/${workspaceId}/share`;
    setLoading(true);
    try {
      const data = await cachedGet(key, () => api.get(key).then((res) => res.data));
      setLinks(data);
    } catch (err) {
      console.error('Error fetching shared links', err);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
fetchLinks();
  }, [fetchLinks]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const response = await api.post(`/workspaces/${workspaceId}/share`, {
        role,
        expires_at: resolveExpiresAt(expiryPreset, customExpiresAt),
        password: password.trim() || null,
        invite_email: inviteEmail.trim() || null,
      });
      invalidate(`/workspaces/${workspaceId}/share`);
      setLinks((prev) => [...prev, response.data]);
      setRole('member');
      setExpiryPreset('none');
      setCustomExpiresAt('');
      setPassword('');
      setInviteEmail('');
      toast.success('Share link generated.');
    } catch (err) {  
      setError(parseApiError(err, 'Failed to generate share link.'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevoke = async (linkId) => {
    const ok = await confirm({
      title: 'Revoke share link',
      message: 'Revoke this share link? Anyone using it will lose access.',
      confirmText: 'Revoke',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.delete(`/workspaces/share/${linkId}`);
      invalidate(`/workspaces/${workspaceId}/share`);
      setLinks((prev) => prev.filter((l) => l.id !== linkId));
      toast.success('Share link revoked.');
    } catch (err) { // eslint-disable-line no-unused-vars
      toast.error('Failed to revoke share link.');
    }
  };

  const handleCopy = async (link) => {
    const ok = await copyToClipboard(shareUrl(link.id));
    if (ok) {
      setCopiedId(link.id);
      setTimeout(() => setCopiedId(null), 2000);
      toast.success('Share link copied to clipboard.');
    } else {
      toast.error('Could not copy automatically — copy the link manually.');
    }
  };

  return (
    <section className="gc-panel">
      <div className="gc-panel-header">
        <span className="gc-panel-title">
          <Link2 size={15} />
          Shared Links
        </span>
      </div>

      <p className="gc-panel-sub">
        Generate a link so people outside your workspace can request to join it. Opening the link sends a join
        request at the role you choose below — an admin still needs to approve it from the Members tab before
        access is granted.
      </p>

      {isAdmin && (
        <form
          onSubmit={handleCreate}
          className="gc-flex-row-end"
        >
          <div className="gc-flex-grow-140">
            <label htmlFor="share-role" className="gc-label">Joins as</label>
            <select id="share-role" className="gc-select" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="admin">Admin</option>
              <option value="member">Member</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>
          <div className="gc-flex-grow-140">
            <label htmlFor="share-expiry" className="gc-label">Expires</label>
            <select id="share-expiry" className="gc-select" value={expiryPreset} onChange={(e) => setExpiryPreset(e.target.value)}>
              {EXPIRY_PRESETS.map((preset) => (
                <option key={preset.value} value={preset.value}>
                  {preset.label}
                </option>
              ))}
            </select>
          </div>
          {expiryPreset === 'custom' && (
            <div className="gc-flex-grow-180">
              <label htmlFor="share-custom-expiry" className="gc-label">Custom date &amp; time</label>
              <input
                id="share-custom-expiry"
                type="datetime-local"
                className="gc-input"
                value={customExpiresAt}
                onChange={(e) => setCustomExpiresAt(e.target.value)}
              />
            </div>
          )}
          <div className="gc-flex-grow-180">
            <label htmlFor="share-password" className="gc-label">Password (optional)</label>
            <input
              id="share-password"
              type="text"
              className="gc-input"
              placeholder="Leave blank for no password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="gc-flex-grow-180">
            <label htmlFor="share-email" className="gc-label">Email this link to (optional)</label>
            <input
              id="share-email"
              type="email"
              className="gc-input"
              placeholder="person@example.com"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
          </div>
          <button type="submit" disabled={submitting} className="gc-btn gc-btn-primary gc-h-34">
            {submitting ? 'Generating...' : 'Generate Link'}
          </button>
        </form>
      )}

      {isAdmin && (
        <div className="gc-text-desc-muted gc-mt-sm">
          Note: email delivery isn't wired up to a provider yet — for now, copy the link below and send it yourself.
        </div>
      )}

      {error && <div className="gc-form-error">{error}</div>}

      {loading ? (
        <div className="gc-empty">Loading shared links...</div>
      ) : links.length === 0 ? (
        <div className="gc-empty">No active share links for this workspace.</div>
      ) : (
        <div>
          {links.map((link) => (
            <div key={link.id} className="gc-row">
              <div className="gc-min-w-0">
                <div className="gc-row-main gc-font-mono-small">
                  {shareUrl(link.id)}
                </div>
                <div className="gc-row-meta">
                  <span className={`gc-badge ${ROLE_BADGE[link.role] || 'gc-badge-member'}`}>Joins as {link.role}</span>
                  <span>{link.expires_at ? `Expires ${new Date(link.expires_at).toLocaleString()}` : 'Never expires'}</span>
                  {link.has_password && (
                    <span className="gc-badge gc-badge-viewer">
                      <Lock size={10} />
                      Protected
                    </span>
                  )}
                  {link.invite_email && <span>Sent to: {link.invite_email}</span>}
                </div>
              </div>

              <div className="gc-actions-row">
                <button className="gc-btn gc-btn-icon" onClick={() => handleCopy(link)} title="Copy link" type="button">
                  {copiedId === link.id ? <Check size={13} /> : <Copy size={13} />}
                </button>
                {isAdmin && (
                  <button
                    className="gc-btn gc-btn-danger gc-btn-icon"
                    onClick={() => handleRevoke(link.id)}
                    title="Revoke link"
                    type="button"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default SharedLinksTab;
