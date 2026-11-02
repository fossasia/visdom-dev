/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import CheckoutModal from '../CheckoutModal';
import CreateWorkspaceModal from '../CreateWorkspaceModal';
import DeleteWorkspaceModal from '../DeleteWorkspaceModal';
import InviteMemberModal from '../InviteMemberModal';
import SelectWorkspaceModal from '../SelectWorkspaceModal';

// Mock AuthContext
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'user-1' } }),
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

// Mock toast
vi.mock('../../toast/useToast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

describe('Workspace Modals Accessibility', () => {
  it('CreateWorkspaceModal has role="dialog", accessible name, and initial focus on input', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(<CreateWorkspaceModal onClose={handleClose} onCreated={() => {}} />);

    const dialog = screen.getByRole('dialog', { name: 'Create Workspace' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    // AutoFocus input has initial focus
    expect(screen.getByPlaceholderText('NLP Labs')).toHaveFocus();

    // Escape closes modal
    await user.keyboard('{Escape}');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('DeleteWorkspaceModal has role="dialog", danger title as accessible name, and autoFocus on confirmation input', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <DeleteWorkspaceModal
        workspace={{ id: 'ws-123', name: 'Acme Corp' }}
        onClose={handleClose}
        onDeleted={() => {}}
      />
    );

    const dialog = screen.getByRole('dialog', { name: 'Delete Workspace' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    // AutoFocus confirmation input has focus
    expect(screen.getByPlaceholderText('Acme Corp')).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('InviteMemberModal has role="dialog", accessible name, and autoFocus on email input', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(<InviteMemberModal workspaceId="ws-1" onClose={handleClose} onInvited={() => {}} />);

    const dialog = screen.getByRole('dialog', { name: 'Invite Collaborator' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    expect(screen.getByPlaceholderText('teammate@example.com')).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('SelectWorkspaceModal has role="dialog", accessible name, and search input focused', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <SelectWorkspaceModal
        workspaces={[{ id: 'ws-1', name: 'Default', slug: 'default', starred: false }]}
        activeWorkspace={null}
        onClose={handleClose}
        onSwitch={() => {}}
        onCreated={() => {}}
        onWorkspaceUpdated={() => {}}
      />
    );

    const dialog = screen.getByRole('dialog', { name: 'Select a workspace' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    expect(screen.getByPlaceholderText('Search workspaces...')).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('CheckoutModal has role="dialog", accessible name, and close button closes', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <CheckoutModal
        plan={{ id: 'team', name: 'Team' }}
        onClose={handleClose}
        onComplete={() => {}}
      />
    );

    const dialog = screen.getByRole('dialog', { name: 'Upgrade to Team' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    // Close button works
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('preserves nested workspace creation flow inside SelectWorkspaceModal', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <SelectWorkspaceModal
        workspaces={[{ id: 'ws-1', name: 'Default', slug: 'default', starred: false }]}
        activeWorkspace={null}
        onClose={handleClose}
        onSwitch={() => {}}
        onCreated={() => {}}
        onWorkspaceUpdated={() => {}}
      />
    );

    expect(screen.getByRole('dialog', { name: 'Select a workspace' })).toBeInTheDocument();

    const newWsBtn = screen.getByRole('button', { name: /New Workspace/i });

    // Open nested CreateWorkspaceModal
    await user.click(newWsBtn);

    // Both dialogs are mounted, but CreateWorkspaceModal is on top and active
    const createDialog = screen.getByRole('dialog', { name: 'Create Workspace' });
    expect(createDialog).toBeInTheDocument();
    expect(screen.getByPlaceholderText('NLP Labs')).toHaveFocus();

    // Escape closes only the nested CreateWorkspaceModal
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: 'Create Workspace' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Select a workspace' })).toBeInTheDocument();
    expect(handleClose).not.toHaveBeenCalled();

    // Focus is restored to the "New Workspace" button that opened it
    expect(newWsBtn).toHaveFocus();

    // Escape closes SelectWorkspaceModal
    await user.keyboard('{Escape}');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});

