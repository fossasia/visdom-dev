/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DeleteWorkspaceModal from '../DeleteWorkspaceModal';

const mocks = vi.hoisted(() => ({
  api: { delete: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../context/AuthContext', () => ({ api: mocks.api }));
vi.mock('../../toast/useToast', () => ({ useToast: () => mocks.toast }));

describe('DeleteWorkspaceModal', () => {
  const workspace = { id: 'ws-123', name: 'Alpha Lab' };

  const defaultProps = {
    workspace,
    onClose: vi.fn(),
    onDeleted: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderModal = (props = {}) => render(<DeleteWorkspaceModal {...defaultProps} {...props} />);

  describe('what it shows', () => {
    it('renders modal title, warning description, input and disabled submit button', () => {
      renderModal();

      const modalHeader = document.querySelector('.gc-modal-header');
      expect(within(modalHeader).getByText('Delete Workspace')).toBeInTheDocument();
      expect(screen.getByText(/This action/)).toBeInTheDocument();
      expect(screen.getByText(/cannot be undone/)).toBeInTheDocument();
      expect(screen.getByText(/Please type/)).toBeInTheDocument();

      const input = screen.getByPlaceholderText('Alpha Lab');
      expect(input).toBeInTheDocument();
      expect(input).toHaveValue('');

      const submitButton = screen.getByRole('button', { name: 'I understand, delete this workspace' });
      expect(submitButton).toBeInTheDocument();
      expect(submitButton).toBeDisabled();
    });
  });

  describe('what its buttons do', () => {
    it('calls onClose when close button is clicked', async () => {
      const user = userEvent.setup();
      renderModal();

      await user.click(screen.getByRole('button', { name: 'Close' }));

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });

    it('keeps submit button disabled until confirmation name matches exactly', async () => {
      const user = userEvent.setup();
      renderModal();

      const input = screen.getByPlaceholderText('Alpha Lab');
      const submitButton = screen.getByRole('button', { name: 'I understand, delete this workspace' });

      await user.type(input, 'Alpha');
      expect(submitButton).toBeDisabled();

      await user.type(input, ' Lab');
      expect(submitButton).toBeEnabled();

      await user.type(input, ' extra');
      expect(submitButton).toBeDisabled();
    });

    it('deletes workspace and triggers callbacks on success', async () => {
      const user = userEvent.setup();
      mocks.api.delete.mockResolvedValueOnce({});
      renderModal();

      const input = screen.getByPlaceholderText('Alpha Lab');
      await user.type(input, 'Alpha Lab');

      const submitButton = screen.getByRole('button', { name: 'I understand, delete this workspace' });
      await user.click(submitButton);

      expect(mocks.api.delete).toHaveBeenCalledWith('/workspaces/ws-123');
      await waitFor(() => {
        expect(mocks.toast.success).toHaveBeenCalledWith('Workspace "Alpha Lab" deleted.');
      });
      expect(defaultProps.onDeleted).toHaveBeenCalledWith('ws-123');
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });

    it('shows deleting state and disables button while submission is in flight', async () => {
      const user = userEvent.setup();
      let resolveDelete;
      mocks.api.delete.mockReturnValueOnce(
        new Promise((resolve) => {
          resolveDelete = resolve;
        })
      );
      renderModal();

      const input = screen.getByPlaceholderText('Alpha Lab');
      await user.type(input, 'Alpha Lab');
      await user.click(screen.getByRole('button', { name: 'I understand, delete this workspace' }));

      const submitButton = screen.getByRole('button', { name: 'Deleting...' });
      expect(submitButton).toBeDisabled();

      resolveDelete({});
      await waitFor(() => {
        expect(defaultProps.onClose).toHaveBeenCalled();
      });
    });
  });

  describe('how it handles an error from the API', () => {
    it('displays error details returned by API and preserves modal state', async () => {
      const user = userEvent.setup();
      mocks.api.delete.mockRejectedValueOnce({
        response: { data: { detail: 'Only organization administrators can delete this workspace.' } },
      });
      renderModal();

      const input = screen.getByPlaceholderText('Alpha Lab');
      await user.type(input, 'Alpha Lab');
      await user.click(screen.getByRole('button', { name: 'I understand, delete this workspace' }));

      expect(
        await screen.findByText('Only organization administrators can delete this workspace.')
      ).toBeInTheDocument();
      expect(defaultProps.onDeleted).not.toHaveBeenCalled();
      expect(defaultProps.onClose).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'I understand, delete this workspace' })).toBeEnabled();
    });

    it('displays fallback error message when API fails without detail', async () => {
      const user = userEvent.setup();
      mocks.api.delete.mockRejectedValueOnce(new Error('Network error'));
      renderModal();

      const input = screen.getByPlaceholderText('Alpha Lab');
      await user.type(input, 'Alpha Lab');
      await user.click(screen.getByRole('button', { name: 'I understand, delete this workspace' }));

      expect(await screen.findByText('Failed to delete workspace.')).toBeInTheDocument();
      expect(defaultProps.onDeleted).not.toHaveBeenCalled();
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });
  });
});

