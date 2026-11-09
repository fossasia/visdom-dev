/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../../context/AuthContext';
import { useToast } from '../toast/useToast';
import { parseApiError } from '../../utils/helpers';
import ModalPortal from '../ModalPortal';

const slugify = (value) =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

const CreateWorkspaceModal = ({ onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();

  const handleNameChange = (e) => {
    const value = e.target.value;
    setName(value);
    if (!slugTouched) {
      setSlug(slugify(value));
    }
  };

  const handleSlugChange = (e) => {
    setSlugTouched(true);
    setSlug(slugify(e.target.value));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim() || !slug.trim()) return;

    setSubmitting(true);
    setError('');
    try {
      const response = await api.post('/workspaces', { name: name.trim(), slug: slug.trim() });
      toast.success(`Workspace "${response.data.name}" created.`);
      onCreated(response.data);
    } catch (err) {
      setError(parseApiError(err, 'Failed to create workspace.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalPortal onClose={onClose}>
      <div className="gc-modal-header">
        <span className="gc-modal-title">Create Workspace</span>
        <button className="gc-modal-close" onClick={onClose} type="button" aria-label="Close">
          <X size={16} />
        </button>
      </div>

      {error && <div className="gc-form-error">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="gc-field">
          <label className="gc-label">Workspace Name</label>
          <input
            type="text"
            required
            autoFocus
            className="gc-input"
            placeholder="NLP Labs"
            value={name}
            onChange={handleNameChange}
          />
        </div>

        <div className="gc-field">
          <label className="gc-label">Slug</label>
          <input
            type="text"
            required
            className="gc-input"
            placeholder="nlp-labs"
            value={slug}
            onChange={handleSlugChange}
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="gc-btn gc-btn-primary gc-w-full gc-mt-1"
        >
          {submitting ? 'Creating...' : 'Create Workspace'}
        </button>
      </form>
    </ModalPortal>
  );
};

export default CreateWorkspaceModal;
