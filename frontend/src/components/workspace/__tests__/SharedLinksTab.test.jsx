/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SharedLinksTab from '../SharedLinksTab';
import { clearRequestCache } from '../../../utils/requestCache';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  confirm: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
  copyToClipboard: vi.fn(),
}));

vi.mock('../../../context/AuthContext', () => ({ api: mocks.api }));
vi.mock('../../../context/ConfirmContext', () => ({ useConfirm: () => mocks.confirm }));
vi.mock('../../toast/useToast', () => ({ useToast: () => mocks.toast }));
vi.mock('../../../utils/clipboard', () => ({
  copyToClipboard: mocks.copyToClipboard,
}));

describe('SharedLinksTab', () => {
  const workspaceId = 'ws-test-1';

  const sampleLinks = [
    {
      id: 'link-1',
      role: 'member',
      expires_at: null,
      has_password: false,
      invite_email: null,
    },
    {
      id: 'link-2',
      role: 'viewer',
      expires_at: '2027-01-01T00:00:00Z',
      has_password: true,
      invite_email: 'collaborator@example.com',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    clearRequestCache();
    mocks.api.get.mockResolvedValue({ data: sampleLinks });
  });

  const renderTab = (props = {}) =>
    render(<SharedLinksTab workspaceId={workspaceId} isAdmin={true} {...props} />);

  describe('loading and empty states', () => {
    it('shows loading indicator while fetching links', () => {
      mocks.api.get.mockReturnValue(new Promise(() => {}));
      renderTab();

      expect(screen.getByText('Loading shared links...')).toBeInTheDocument();
    });

    it('shows empty message when there are no links', async () => {
      mocks.api.get.mockResolvedValue({ data: [] });
      renderTab();

      expect(
        await screen.findByText('No active share links for this workspace.')
      ).toBeInTheDocument();
    });
  });

  describe('rendering shared links', () => {
    it('renders each link with url, role, expiration, password protection and recipient', async () => {
      renderTab();

      expect(await screen.findByText(`${window.location.origin}/share/link-1`)).toBeInTheDocument();
      const link1Row = screen.getByText(`${window.location.origin}/share/link-1`).closest('.gc-row');
      expect(within(link1Row).getByText('Joins as member')).toBeInTheDocument();
      expect(within(link1Row).getByText('Never expires')).toBeInTheDocument();

      expect(screen.getByText(`${window.location.origin}/share/link-2`)).toBeInTheDocument();
      const link2Row = screen.getByText(`${window.location.origin}/share/link-2`).closest('.gc-row');
      expect(within(link2Row).getByText('Joins as viewer')).toBeInTheDocument();
      expect(within(link2Row).getByText('Protected')).toBeInTheDocument();
      expect(within(link2Row).getByText('Sent to: collaborator@example.com')).toBeInTheDocument();
      expect(within(link2Row).getByText(/Expires/)).toBeInTheDocument();
    });
  });

  describe('role and admin permissions', () => {
    it('hides creation form and revoke buttons for non-admin users', async () => {
      renderTab({ isAdmin: false });

      await screen.findByText(`${window.location.origin}/share/link-1`);

      expect(screen.queryByRole('button', { name: 'Generate Link' })).not.toBeInTheDocument();
      expect(screen.queryByTitle('Revoke link')).not.toBeInTheDocument();
      expect(screen.getAllByTitle('Copy link')).toHaveLength(2);
    });

    it('renders creation form and revoke buttons for admin users', async () => {
      renderTab({ isAdmin: true });

      await screen.findByText(`${window.location.origin}/share/link-1`);

      expect(screen.getByRole('button', { name: 'Generate Link' })).toBeInTheDocument();
      expect(screen.getAllByTitle('Revoke link')).toHaveLength(2);
      expect(
        screen.getByText(/Note: email delivery isn't wired up to a provider yet/)
      ).toBeInTheDocument();
    });
  });

  describe('generating a shared link', () => {
    it('generates a link with default options (member, never expires, no password)', async () => {
      const user = userEvent.setup();
      const newLink = {
        id: 'link-new',
        role: 'member',
        expires_at: null,
        has_password: false,
        invite_email: null,
      };
      mocks.api.post.mockResolvedValue({ data: newLink });
      renderTab({ isAdmin: true });

      await screen.findByText(`${window.location.origin}/share/link-1`);

      await user.click(screen.getByRole('button', { name: 'Generate Link' }));

      expect(mocks.api.post).toHaveBeenCalledWith(
        `/workspaces/${workspaceId}/share`,
        {
          role: 'member',
          expires_at: null,
          password: null,
          invite_email: null,
        }
      );
      expect(await screen.findByText(`${window.location.origin}/share/link-new`)).toBeInTheDocument();
      expect(mocks.toast.success).toHaveBeenCalledWith('Share link generated.');
    });

    it('generates a link with custom expiration, password, and recipient email', async () => {
      const user = userEvent.setup();
      const newLink = {
        id: 'link-custom',
        role: 'admin',
        expires_at: '2026-12-31T23:59:00.000Z',
        has_password: true,
        invite_email: 'newuser@example.com',
      };
      mocks.api.post.mockResolvedValue({ data: newLink });
      renderTab({ isAdmin: true });

      await screen.findByText(`${window.location.origin}/share/link-1`);

      const [roleSelect, expirySelect] = screen.getAllByRole('combobox');
      await user.selectOptions(roleSelect, 'admin');
      await user.selectOptions(expirySelect, 'custom');

      const dateInput = document.querySelector('input[type="datetime-local"]');
      await user.type(dateInput, '2026-12-31T23:59');

      await user.type(screen.getByPlaceholderText('Leave blank for no password'), 'secretPass123');
      await user.type(screen.getByPlaceholderText('person@example.com'), 'newuser@example.com');

      await user.click(screen.getByRole('button', { name: 'Generate Link' }));

      expect(mocks.api.post).toHaveBeenCalledWith(
        `/workspaces/${workspaceId}/share`,
        expect.objectContaining({
          role: 'admin',
          expires_at: new Date('2026-12-31T23:59').toISOString(),
          password: 'secretPass123',
          invite_email: 'newuser@example.com',
        })
      );
      expect(await screen.findByText(`${window.location.origin}/share/link-custom`)).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Leave blank for no password')).toHaveValue('');
      expect(screen.getByPlaceholderText('person@example.com')).toHaveValue('');
    });

    it('shows error banner when link generation fails', async () => {
      const user = userEvent.setup();
      mocks.api.post.mockRejectedValue({
        response: { data: { detail: 'Only workspace admins can generate share links.' } },
      });
      renderTab({ isAdmin: true });

      await screen.findByText(`${window.location.origin}/share/link-1`);

      await user.click(screen.getByRole('button', { name: 'Generate Link' }));

      expect(
        await screen.findByText('Only workspace admins can generate share links.')
      ).toBeInTheDocument();
    });
  });

  describe('revoking a shared link', () => {
    it('does not revoke link when confirmation is cancelled', async () => {
      const user = userEvent.setup();
      mocks.confirm.mockResolvedValue(false);
      renderTab({ isAdmin: true });

      await screen.findByText(`${window.location.origin}/share/link-1`);
      const revokeButtons = screen.getAllByTitle('Revoke link');
      await user.click(revokeButtons[0]);

      expect(mocks.confirm).toHaveBeenCalledWith(
        expect.objectContaining({ danger: true, title: 'Revoke share link' })
      );
      expect(mocks.api.delete).not.toHaveBeenCalled();
      expect(screen.getByText(`${window.location.origin}/share/link-1`)).toBeInTheDocument();
    });

    it('deletes link and removes it from the list when confirmed', async () => {
      const user = userEvent.setup();
      mocks.confirm.mockResolvedValue(true);
      mocks.api.delete.mockResolvedValue({});
      renderTab({ isAdmin: true });

      await screen.findByText(`${window.location.origin}/share/link-1`);
      const revokeButtons = screen.getAllByTitle('Revoke link');
      await user.click(revokeButtons[0]);

      await waitFor(() => {
        expect(mocks.api.delete).toHaveBeenCalledWith('/workspaces/share/link-1');
        expect(mocks.toast.success).toHaveBeenCalledWith('Share link revoked.');
      });
      expect(screen.queryByText(`${window.location.origin}/share/link-1`)).not.toBeInTheDocument();
    });

    it('displays error toast when revoking fails', async () => {
      const user = userEvent.setup();
      mocks.confirm.mockResolvedValue(true);
      mocks.api.delete.mockRejectedValue(new Error('Server error'));
      renderTab({ isAdmin: true });

      await screen.findByText(`${window.location.origin}/share/link-1`);
      const revokeButtons = screen.getAllByTitle('Revoke link');
      await user.click(revokeButtons[0]);

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith('Failed to revoke share link.');
      });
      expect(screen.getByText(`${window.location.origin}/share/link-1`)).toBeInTheDocument();
    });
  });

  describe('copying a link to clipboard', () => {
    it('copies the share link url and notifies user on success', async () => {
      const user = userEvent.setup();
      mocks.copyToClipboard.mockResolvedValue(true);
      renderTab();

      await screen.findByText(`${window.location.origin}/share/link-1`);
      const copyButtons = screen.getAllByTitle('Copy link');
      await user.click(copyButtons[0]);

      expect(mocks.copyToClipboard).toHaveBeenCalledWith(`${window.location.origin}/share/link-1`);
      expect(mocks.toast.success).toHaveBeenCalledWith('Share link copied to clipboard.');
    });

    it('displays error toast when clipboard copying fails', async () => {
      const user = userEvent.setup();
      mocks.copyToClipboard.mockResolvedValue(false);
      renderTab();

      await screen.findByText(`${window.location.origin}/share/link-1`);
      const copyButtons = screen.getAllByTitle('Copy link');
      await user.click(copyButtons[0]);

      expect(mocks.copyToClipboard).toHaveBeenCalledWith(`${window.location.origin}/share/link-1`);
      expect(mocks.toast.error).toHaveBeenCalledWith(
        'Could not copy automatically — copy the link manually.'
      );
    });
  });
});
