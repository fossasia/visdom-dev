/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WorkspaceSettingsTab from '../WorkspaceSettingsTab';

const mocks = vi.hoisted(() => ({
  api: { delete: vi.fn() },
  confirm: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../context/AuthContext', () => ({ api: mocks.api }));
vi.mock('../../../context/ConfirmContext', () => ({ useConfirm: () => mocks.confirm }));
vi.mock('../../toast/useToast', () => ({ useToast: () => mocks.toast }));
vi.mock('../DeleteWorkspaceModal', () => ({
  default: ({ workspace, onClose, onDeleted }) => (
    <div data-testid="delete-workspace-modal">
      <span>Modal for {workspace.name}</span>
      <button onClick={onClose} type="button">
        Close Delete Modal
      </button>
      <button onClick={() => onDeleted(workspace.id)} type="button">
        Confirm Delete
      </button>
    </div>
  ),
}));

describe('WorkspaceSettingsTab', () => {
  const workspace = {
    id: 'ws-1',
    name: 'Alpha Lab',
    slug: 'alpha-lab',
    created_by: 'user-owner',
  };

  const defaultProps = {
    workspace,
    isAdmin: false,
    currentUserId: 'user-member',
    retention: null,
    onDeleted: vi.fn(),
    onLeave: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderTab = (props = {}) => render(<WorkspaceSettingsTab {...defaultProps} {...props} />);

  describe('what it shows', () => {
    it('renders workspace details in settings grid', () => {
      renderTab();

      expect(screen.getByText('Workspace Settings')).toBeInTheDocument();
      expect(screen.getByText('Workspace Name')).toBeInTheDocument();
      expect(screen.getByText('Alpha Lab')).toBeInTheDocument();
      expect(screen.getByText('Slug')).toBeInTheDocument();
      expect(screen.getByText('alpha-lab')).toBeInTheDocument();
      expect(screen.getByText('Workspace ID')).toBeInTheDocument();
      expect(screen.getByText('ws-1')).toBeInTheDocument();
    });

    it('shows owner membership notice when current user created the workspace', () => {
      renderTab({ currentUserId: 'user-owner' });

      expect(
        screen.getByText(
          'You own this workspace, so no one else can remove you. To leave it with someone else in charge, make them the owner from the Members tab first.'
        )
      ).toBeInTheDocument();
    });

    it('shows member notice when current user is not the owner', () => {
      renderTab({ currentUserId: 'user-member' });

      expect(screen.getByText('You can leave this workspace at any time.')).toBeInTheDocument();
    });

    it('renders retention and expiring environments when retention notice is provided', () => {
      renderTab({
        retention: {
          state: 'active',
          days: 30,
          warn_days: 7,
          expiring: ['env-1', 'env-2'],
          plan: 'Team',
        },
      });

      expect(screen.getByText('History')).toBeInTheDocument();
      expect(
        screen.getByText(
          "Environments not updated for 30 days are removed, on the owner's Team plan. The main environment is always kept."
        )
      ).toBeInTheDocument();
      expect(screen.getByText('These go within the next 7 days unless they are updated:')).toBeInTheDocument();
      expect(screen.getByText('env-1')).toBeInTheDocument();
      expect(screen.getByText('env-2')).toBeInTheDocument();
    });

    it('does not render retention section when retention prop is not provided', () => {
      renderTab({ retention: null });

      expect(screen.queryByText('History')).not.toBeInTheDocument();
    });

    it('shows Danger Zone and Delete Workspace button when user is an admin', () => {
      renderTab({ isAdmin: true });

      expect(screen.getByText('Danger Zone')).toBeInTheDocument();
      expect(
        screen.getByText('Deleting a workspace permanently removes its plots, memberships and shared links.')
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Delete Workspace' })).toBeInTheDocument();
    });

    it('hides Danger Zone when user is not an admin', () => {
      renderTab({ isAdmin: false });

      expect(screen.queryByText('Danger Zone')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Delete Workspace' })).not.toBeInTheDocument();
    });
  });

  describe('what its buttons do', () => {
    it('prompts confirmation and leaves workspace when confirmed', async () => {
      const user = userEvent.setup();
      mocks.confirm.mockResolvedValueOnce(true);
      mocks.api.delete.mockResolvedValueOnce({});
      renderTab();

      await user.click(screen.getByRole('button', { name: 'Leave Workspace' }));

      expect(mocks.confirm).toHaveBeenCalledWith({
        title: 'Leave workspace',
        message: 'Leave "Alpha Lab"? You\'ll lose access until you\'re invited back.',
        confirmText: 'Leave',
        danger: true,
      });
      expect(mocks.api.delete).toHaveBeenCalledWith('/workspaces/ws-1/members/user-member');
      await waitFor(() => {
        expect(mocks.toast.success).toHaveBeenCalledWith('You left "Alpha Lab".');
      });
      expect(defaultProps.onLeave).toHaveBeenCalledWith('ws-1');
    });

    it('does not leave workspace if confirmation is rejected', async () => {
      const user = userEvent.setup();
      mocks.confirm.mockResolvedValueOnce(false);
      renderTab();

      await user.click(screen.getByRole('button', { name: 'Leave Workspace' }));

      expect(mocks.confirm).toHaveBeenCalled();
      expect(mocks.api.delete).not.toHaveBeenCalled();
      expect(defaultProps.onLeave).not.toHaveBeenCalled();
    });

    it('shows leaving state and disables button while leave request is in flight', async () => {
      const user = userEvent.setup();
      let resolveLeave;
      mocks.confirm.mockResolvedValueOnce(true);
      mocks.api.delete.mockReturnValueOnce(
        new Promise((resolve) => {
          resolveLeave = resolve;
        })
      );
      renderTab();

      await user.click(screen.getByRole('button', { name: 'Leave Workspace' }));

      const leaveButton = screen.getByRole('button', { name: 'Leaving...' });
      expect(leaveButton).toBeDisabled();

      resolveLeave({});
      await waitFor(() => {
        expect(defaultProps.onLeave).toHaveBeenCalledWith('ws-1');
      });
    });

    it('opens and closes Delete Workspace modal', async () => {
      const user = userEvent.setup();
      renderTab({ isAdmin: true });

      expect(screen.queryByTestId('delete-workspace-modal')).not.toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Delete Workspace' }));
      expect(screen.getByTestId('delete-workspace-modal')).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Close Delete Modal' }));
      expect(screen.queryByTestId('delete-workspace-modal')).not.toBeInTheDocument();
    });

    it('forwards onDeleted callback from Delete Workspace modal', async () => {
      const user = userEvent.setup();
      renderTab({ isAdmin: true });

      await user.click(screen.getByRole('button', { name: 'Delete Workspace' }));
      await user.click(screen.getByRole('button', { name: 'Confirm Delete' }));

      expect(defaultProps.onDeleted).toHaveBeenCalledWith('ws-1');
    });
  });

  describe('how it handles an error from the API', () => {
    it('shows error toast with API detail when leaving fails', async () => {
      const user = userEvent.setup();
      mocks.confirm.mockResolvedValueOnce(true);
      mocks.api.delete.mockRejectedValueOnce({
        response: { data: { detail: 'Only non-owners can leave without transferring ownership.' } },
      });
      renderTab();

      await user.click(screen.getByRole('button', { name: 'Leave Workspace' }));

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith('Only non-owners can leave without transferring ownership.');
      });
      expect(defaultProps.onLeave).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Leave Workspace' })).toBeEnabled();
    });

    it('shows fallback error toast when leaving fails without detail', async () => {
      const user = userEvent.setup();
      mocks.confirm.mockResolvedValueOnce(true);
      mocks.api.delete.mockRejectedValueOnce(new Error('Network error'));
      renderTab();

      await user.click(screen.getByRole('button', { name: 'Leave Workspace' }));

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith('Failed to leave workspace.');
      });
      expect(defaultProps.onLeave).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Leave Workspace' })).toBeEnabled();
    });
  });
});

