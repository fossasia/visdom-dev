/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PendingInvitesBanner from '../PendingInvitesBanner';

const { mockPost, mockDelete, mockConfirm, mockToastSuccess, mockToastError, mockToastInfo } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
  mockConfirm: vi.fn(),
  mockToastSuccess: vi.fn(),
  mockToastError: vi.fn(),
  mockToastInfo: vi.fn(),
}));

vi.mock('../../../context/AuthContext', () => ({
  api: {
    post: mockPost,
    delete: mockDelete,
  },
}));

vi.mock('../../../context/ConfirmContext', () => ({
  useConfirm: () => mockConfirm,
}));

vi.mock('../../toast/useToast', () => ({
  useToast: () => ({
    success: mockToastSuccess,
    error: mockToastError,
    info: mockToastInfo,
  }),
}));

describe('PendingInvitesBanner', () => {
  const sampleInvites = [
    {
      workspace: { id: 'ws-1', name: 'Vision Lab' },
      role: 'member',
    },
    {
      workspace: { id: 'ws-2', name: 'NLP Research' },
      role: 'admin',
    },
  ];

  const defaultProps = {
    invites: sampleInvites,
    currentUserId: 'user-current-123',
    onAccepted: vi.fn(),
    onDeclined: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderBanner = (props = {}) => render(<PendingInvitesBanner {...defaultProps} {...props} />);

  describe('what it shows', () => {
    it('returns null when invites is empty', () => {
      const { container } = renderBanner({ invites: [] });
      expect(container.firstChild).toBeNull();
    });

    it('returns null when invites is null or undefined', () => {
      const { container: containerNull } = renderBanner({ invites: null });
      expect(containerNull.firstChild).toBeNull();

      const { container: containerUndef } = renderBanner({ invites: undefined });
      expect(containerUndef.firstChild).toBeNull();
    });

    it('renders the banner header with invite count', () => {
      renderBanner();

      expect(screen.getByText('Pending Invitations (2)')).toBeInTheDocument();
    });

    it('renders workspace names and role descriptions for each invite', () => {
      renderBanner();

      expect(screen.getByText('Vision Lab')).toBeInTheDocument();
      expect(screen.getByText("You've been invited to join as member")).toBeInTheDocument();

      expect(screen.getByText('NLP Research')).toBeInTheDocument();
      expect(screen.getByText("You've been invited to join as admin")).toBeInTheDocument();
    });

    it('renders accept and decline action buttons for all invites', () => {
      renderBanner();

      const acceptButtons = screen.getAllByTitle('Accept invite');
      const declineButtons = screen.getAllByTitle('Decline invite');

      expect(acceptButtons).toHaveLength(2);
      expect(declineButtons).toHaveLength(2);
    });
  });

  describe('accepting invitations', () => {
    it('submits accept request, shows success toast and calls onAccepted callback', async () => {
      const user = userEvent.setup();
      mockPost.mockResolvedValueOnce({ data: { ok: true } });

      renderBanner();

      const acceptButtons = screen.getAllByTitle('Accept invite');
      await user.click(acceptButtons[0]);

      expect(mockPost).toHaveBeenCalledTimes(1);
      expect(mockPost).toHaveBeenCalledWith('/workspaces/ws-1/members/me/accept');

      expect(mockToastSuccess).toHaveBeenCalledWith('Joined "Vision Lab".');
      expect(defaultProps.onAccepted).toHaveBeenCalledWith('ws-1');
    });

    it('disables the buttons while the accept request is in flight', async () => {
      const user = userEvent.setup();
      let resolveApi;
      mockPost.mockImplementationOnce(() => new Promise((resolve) => {
        resolveApi = resolve;
      }));

      renderBanner();

      const acceptButtons = screen.getAllByTitle('Accept invite');
      const declineButtons = screen.getAllByTitle('Decline invite');

      await user.click(acceptButtons[0]);

      expect(acceptButtons[0]).toBeDisabled();
      expect(declineButtons[0]).toBeDisabled();

      // other workspace buttons remain enabled
      expect(acceptButtons[1]).not.toBeDisabled();
      expect(declineButtons[1]).not.toBeDisabled();

      resolveApi({ data: { ok: true } });

      await waitFor(() => {
        expect(acceptButtons[0]).not.toBeDisabled();
      });
    });

    it('displays error toast when the accept request fails', async () => {
      const user = userEvent.setup();
      mockPost.mockRejectedValueOnce({
        response: { data: { detail: 'Invitation has expired or is invalid.' } },
      });

      renderBanner();

      const acceptButtons = screen.getAllByTitle('Accept invite');
      await user.click(acceptButtons[0]);

      expect(mockToastError).toHaveBeenCalledWith('Invitation has expired or is invalid.');
      expect(defaultProps.onAccepted).not.toHaveBeenCalled();
    });
  });

  describe('declining invitations', () => {
    it('triggers confirmation dialog with correct warning parameters', async () => {
      const user = userEvent.setup();
      mockConfirm.mockResolvedValueOnce(false);

      renderBanner();

      const declineButtons = screen.getAllByTitle('Decline invite');
      await user.click(declineButtons[0]);

      expect(mockConfirm).toHaveBeenCalledWith({
        title: 'Decline invitation',
        message: 'Decline the invitation to join "Vision Lab"?',
        confirmText: 'Decline',
        danger: true,
      });
    });

    it('does not send delete request when user cancels the confirmation dialog', async () => {
      const user = userEvent.setup();
      mockConfirm.mockResolvedValueOnce(false);

      renderBanner();

      const declineButtons = screen.getAllByTitle('Decline invite');
      await user.click(declineButtons[0]);

      expect(mockDelete).not.toHaveBeenCalled();
      expect(defaultProps.onDeclined).not.toHaveBeenCalled();
    });

    it('submits delete request, shows info toast and calls onDeclined callback when confirmed', async () => {
      const user = userEvent.setup();
      mockConfirm.mockResolvedValueOnce(true);
      mockDelete.mockResolvedValueOnce({ data: { ok: true } });

      renderBanner();

      const declineButtons = screen.getAllByTitle('Decline invite');
      await user.click(declineButtons[0]);

      expect(mockDelete).toHaveBeenCalledTimes(1);
      expect(mockDelete).toHaveBeenCalledWith('/workspaces/ws-1/members/user-current-123');

      expect(mockToastInfo).toHaveBeenCalledWith('Invitation to "Vision Lab" declined.');
      expect(defaultProps.onDeclined).toHaveBeenCalledWith('ws-1');
    });

    it('disables the buttons while the decline request is in flight', async () => {
      const user = userEvent.setup();
      mockConfirm.mockResolvedValueOnce(true);
      let resolveApi;
      mockDelete.mockImplementationOnce(() => new Promise((resolve) => {
        resolveApi = resolve;
      }));

      renderBanner();

      const acceptButtons = screen.getAllByTitle('Accept invite');
      const declineButtons = screen.getAllByTitle('Decline invite');

      await user.click(declineButtons[0]);

      expect(acceptButtons[0]).toBeDisabled();
      expect(declineButtons[0]).toBeDisabled();

      resolveApi({ data: { ok: true } });

      await waitFor(() => {
        expect(declineButtons[0]).not.toBeDisabled();
      });
    });

    it('displays error toast when the decline request fails', async () => {
      const user = userEvent.setup();
      mockConfirm.mockResolvedValueOnce(true);
      mockDelete.mockRejectedValueOnce({
        response: { data: { detail: 'Permission denied.' } },
      });

      renderBanner();

      const declineButtons = screen.getAllByTitle('Decline invite');
      await user.click(declineButtons[0]);

      expect(mockToastError).toHaveBeenCalledWith('Permission denied.');
      expect(defaultProps.onDeclined).not.toHaveBeenCalled();
    });
  });
});
