/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../../context/AuthContext';
import { useToast } from '../toast/useToast';
import { parseApiError } from '../../utils/helpers';
import ModalPortal from '../ModalPortal';

const InviteMemberModal = ({ workspaceId, onClose, onInvited }) => {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('member');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;

    setSubmitting(true);
    setError('');
    try {
      const response = await api.post(`/workspaces/${workspaceId}/members`, {
        email: email.trim(),
        role,
      });
      toast.success(`Invitation sent to ${email.trim()}.`);
      onInvited(response.data);
    } catch (err) {
      setError(parseApiError(err, 'Failed to invite member.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalPortal onClose={onClose}>
      <div className="gc-modal-header">
        <span className="gc-modal-title">Invite Collaborator</span>
        <button className="gc-modal-close" onClick={onClose} type="button">
          <X size={16} />
        </button>
      </div>

      {error && <div className="gc-form-error">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="gc-field">
          <label htmlFor="member-email" className="gc-label">Email Address</label>
          <input
            id="member-email"
            type="email"
            required
            autoFocus
            className="gc-input"
            placeholder="teammate@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="gc-field">
          <label htmlFor="member-role" className="gc-label">Role</label>
          <select id="member-role" className="gc-select" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="admin">Admin</option>
            <option value="member">Member</option>
            <option value="viewer">Viewer</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="gc-btn gc-btn-primary gc-w-full gc-mt-1"
        >
          {submitting ? 'Sending Invite...' : 'Send Invite'}
        </button>
      </form>
    </ModalPortal>
  );
};

export default InviteMemberModal;
