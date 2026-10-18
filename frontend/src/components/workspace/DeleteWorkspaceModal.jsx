/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { api } from '../../context/AuthContext';
import { useToast } from '../toast/useToast';
import { parseApiError } from '../../utils/helpers';
import ModalPortal from '../ModalPortal';

const DeleteWorkspaceModal = ({ workspace, onClose, onDeleted }) => {
  const [confirmText, setConfirmText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();

  const isMatch = confirmText === workspace.name;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isMatch) return;

    setSubmitting(true);
    setError('');
    try {
      await api.delete(`/workspaces/${workspace.id}`);
      toast.success(`Workspace "${workspace.name}" deleted.`);
      onDeleted(workspace.id);
      onClose();
    } catch (err) {
      setError(parseApiError(err, 'Failed to delete workspace.'));
      setSubmitting(false);
    }
  };

  return (
    <ModalPortal onClose={onClose}>
      <div className="gc-modal-header">
        <span className="gc-modal-title gc-text-danger">
          Delete Workspace
        </span>
        <button className="gc-modal-close" onClick={onClose} type="button">
          <X size={16} />
        </button>
      </div>

      <div className="gc-warning-box">
        <AlertTriangle size={16} className="gc-warning-icon" />
        <p className="gc-warning-text">
          This action <strong>cannot be undone</strong>. This will permanently delete the{' '}
          <strong>{workspace.name}</strong> workspace, along with all of its plots, memberships, API access, and
          shared links.
        </p>
      </div>

      {error && <div className="gc-form-error">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="gc-field">
          <label className="gc-label">
            Please type <strong>{workspace.name}</strong> to confirm.
          </label>
          <input
            type="text"
            autoFocus
            className="gc-input"
            placeholder={workspace.name}
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        <button
          type="submit"
          disabled={!isMatch || submitting}
          className="gc-btn gc-btn-danger gc-w-full gc-mt-1"
        >
          {submitting ? 'Deleting...' : 'I understand, delete this workspace'}
        </button>
      </form>
    </ModalPortal>
  );
};

export default DeleteWorkspaceModal;
