/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CreateWorkspaceModal from '../CreateWorkspaceModal';

const mocks = vi.hoisted(() => ({
  api: { post: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../context/AuthContext', () => ({ api: mocks.api }));
vi.mock('../../toast/useToast', () => ({ useToast: () => mocks.toast }));

describe('CreateWorkspaceModal', () => {
  const defaultProps = {
    onClose: vi.fn(),
    onCreated: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderModal = (props = {}) => render(<CreateWorkspaceModal {...defaultProps} {...props} />);

  describe('what it shows', () => {
    it('renders modal header, labels, inputs and submit button', () => {
      renderModal();

      const modalHeader = document.querySelector('.gc-modal-header');
      expect(within(modalHeader).getByText('Create Workspace')).toBeInTheDocument();
      expect(screen.getByText('Workspace Name')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('NLP Labs')).toBeInTheDocument();
      expect(screen.getByText('Slug')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('nlp-labs')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Create Workspace' })).toBeInTheDocument();
    });
  });

  describe('what its buttons do', () => {
    it('calls onClose when clicking the close button', async () => {
      const user = userEvent.setup();
      renderModal();

      const closeButton = document.querySelector('.gc-modal-close');
      await user.click(closeButton);

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });

    it('automatically generates slug from workspace name while slug has not been touched', async () => {
      const user = userEvent.setup();
      renderModal();

      const nameInput = screen.getByPlaceholderText('NLP Labs');
      const slugInput = screen.getByPlaceholderText('nlp-labs');

      await user.type(nameInput, 'Vision & AI Team!');

      expect(slugInput).toHaveValue('vision-ai-team');
    });

    it('preserves custom slug once manually modified', async () => {
      const user = userEvent.setup();
      renderModal();

      const nameInput = screen.getByPlaceholderText('NLP Labs');
      const slugInput = screen.getByPlaceholderText('nlp-labs');

      await user.click(slugInput);
      await user.paste('custom-slug');
      await user.clear(nameInput);
      await user.type(nameInput, 'New Lab Name');

      expect(slugInput).toHaveValue('custom-slug');
    });

    it('does not submit when fields contain only whitespace', async () => {
      const user = userEvent.setup();
      renderModal();

      await user.type(screen.getByPlaceholderText('NLP Labs'), '   ');
      await user.click(screen.getByRole('button', { name: 'Create Workspace' }));

      expect(mocks.api.post).not.toHaveBeenCalled();
    });

    it('creates workspace and notifies caller on submit', async () => {
      const user = userEvent.setup();
      const newWorkspace = { id: 'ws-123', name: 'Robotics', slug: 'robotics' };
      mocks.api.post.mockResolvedValueOnce({ data: newWorkspace });
      renderModal();

      await user.type(screen.getByPlaceholderText('NLP Labs'), 'Robotics');
      await user.click(screen.getByRole('button', { name: 'Create Workspace' }));

      expect(mocks.api.post).toHaveBeenCalledWith('/workspaces', {
        name: 'Robotics',
        slug: 'robotics',
      });
      await waitFor(() => {
        expect(mocks.toast.success).toHaveBeenCalledWith('Workspace "Robotics" created.');
      });
      expect(defaultProps.onCreated).toHaveBeenCalledWith(newWorkspace);
    });

    it('shows creating state and disables button while submitting', async () => {
      const user = userEvent.setup();
      let resolvePost;
      mocks.api.post.mockReturnValueOnce(
        new Promise((resolve) => {
          resolvePost = resolve;
        })
      );
      renderModal();

      await user.type(screen.getByPlaceholderText('NLP Labs'), 'Robotics');
      await user.click(screen.getByRole('button', { name: 'Create Workspace' }));

      const submitButton = screen.getByRole('button', { name: 'Creating...' });
      expect(submitButton).toBeDisabled();

      resolvePost({ data: { id: 'ws-123', name: 'Robotics', slug: 'robotics' } });
      await waitFor(() => {
        expect(defaultProps.onCreated).toHaveBeenCalled();
      });
    });
  });

  describe('how it handles an error from the API', () => {
    it('displays error details returned by the API', async () => {
      const user = userEvent.setup();
      mocks.api.post.mockRejectedValueOnce({
        response: { data: { detail: 'A workspace with this slug already exists.' } },
      });
      renderModal();

      await user.type(screen.getByPlaceholderText('NLP Labs'), 'Robotics');
      await user.click(screen.getByRole('button', { name: 'Create Workspace' }));

      expect(await screen.findByText('A workspace with this slug already exists.')).toBeInTheDocument();
      expect(defaultProps.onCreated).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Create Workspace' })).toBeEnabled();
    });

    it('displays fallback error message when API does not provide details', async () => {
      const user = userEvent.setup();
      mocks.api.post.mockRejectedValueOnce(new Error('Network error'));
      renderModal();

      await user.type(screen.getByPlaceholderText('NLP Labs'), 'Robotics');
      await user.click(screen.getByRole('button', { name: 'Create Workspace' }));

      expect(await screen.findByText('Failed to create workspace.')).toBeInTheDocument();
      expect(defaultProps.onCreated).not.toHaveBeenCalled();
    });
  });
});
