/* Copyright 2017-present, The Visdom Authors */

import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
  logout: vi.fn(), confirm: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../context/AuthContext', () => ({
  api: mocks.api, useAuth: () => ({ logout: mocks.logout }),
}));
vi.mock('../../context/ConfirmContext', () => ({ useConfirm: () => mocks.confirm }));
vi.mock('../toast/useToast', () => ({ useToast: () => mocks.toast }));

import DeleteAccountSection from '../DeleteAccountSection';

const PREVIEW = { blockers: [], leaving_with: [], renewing_plan: null, grace_days: 30 };

const renderSection = () => {
  const onClose = vi.fn();
  render(<DeleteAccountSection onClose={onClose} />);
  return onClose;
};

const startDeletion = async (user) => {
  await user.click(screen.getByRole('button', { name: 'Delete Account' }));
  await user.type(await screen.findByPlaceholderText('Your password'), 'my-secret');
  await user.click(screen.getByRole('button', { name: 'Delete My Account' }));
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.api.get.mockResolvedValue({ data: PREVIEW });
  mocks.confirm.mockResolvedValue(true);
});

describe('DeleteAccountSection', () => {
  it('explains the grace period and waits for the user to start', () => {
    renderSection();

    expect(screen.getByText(/removed for good after 30 days/)).toBeInTheDocument();
    expect(screen.getByText(/Signing in before then cancels it/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete Account' })).toBeEnabled();
    expect(screen.queryByPlaceholderText('Your password')).not.toBeInTheDocument();
    expect(mocks.api.get).not.toHaveBeenCalled();
    expect(mocks.api.post).not.toHaveBeenCalled();
  });

  it('disables the preview button while checking the account', async () => {
    const user = userEvent.setup();
    let resolvePreview;
    mocks.api.get.mockReturnValue(new Promise((resolve) => { resolvePreview = resolve; }));
    renderSection();

    await user.click(screen.getByRole('button', { name: 'Delete Account' }));
    expect(screen.getByRole('button', { name: 'Checking...' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Checking...' }));
    expect(mocks.api.get).toHaveBeenCalledExactlyOnceWith('/auth/me/deletion');

    await act(async () => resolvePreview({ data: PREVIEW }));
    expect(screen.getByRole('button', { name: 'Delete My Account' })).toBeDisabled();
  });

  it('lists workspace blockers and does not offer a deletion form', async () => {
    const user = userEvent.setup();
    mocks.api.get.mockResolvedValue({ data: {
      ...PREVIEW,
      blockers: [
        { id: 'ws-1', name: 'Research', reason: 'You are the only admin.' },
        { id: 'ws-2', name: 'Production', reason: 'Transfer ownership first.' },
      ],
    } });
    renderSection();

    await user.click(screen.getByRole('button', { name: 'Delete Account' }));

    expect(await screen.findByText('Research')).toBeInTheDocument();
    expect(screen.getByText('Production')).toBeInTheDocument();
    expect(screen.getByText(/You are the only admin/)).toBeInTheDocument();
    expect(screen.getByText(/Transfer ownership first/)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Your password')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete My Account' })).not.toBeInTheDocument();
    expect(mocks.api.post).not.toHaveBeenCalled();
  });

  it('shows the returned grace period, renewing plan and workspaces to be deleted', async () => {
    const user = userEvent.setup();
    mocks.api.get.mockResolvedValue({ data: {
      ...PREVIEW, grace_days: 14, renewing_plan: 'Pro',
      leaving_with: [{ id: 'ws-1', name: 'Personal plots' }, { id: 'ws-2', name: 'Experiments' }],
    } });
    renderSection();

    await user.click(screen.getByRole('button', { name: 'Delete Account' }));

    expect(await screen.findByText(/removed for good after 14 days/)).toBeInTheDocument();
    expect(screen.getByText(/Your Pro plan stops renewing now/)).toBeInTheDocument();
    expect(screen.getByText('Personal plots')).toBeInTheDocument();
    expect(screen.getByText('Experiments')).toBeInTheDocument();
  });

  it('omits inapplicable warnings and requires a password', async () => {
    const user = userEvent.setup();
    renderSection();

    await user.click(screen.getByRole('button', { name: 'Delete Account' }));
    const password = await screen.findByPlaceholderText('Your password');

    expect(screen.queryByText(/stops renewing now/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Nobody else uses these workspaces/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete My Account' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Delete My Account' }));
    expect(mocks.confirm).not.toHaveBeenCalled();
    await user.type(password, 'my-secret');
    expect(screen.getByRole('button', { name: 'Delete My Account' })).toBeEnabled();
  });

  it('keeps the account signed in when confirmation is cancelled', async () => {
    const user = userEvent.setup();
    mocks.confirm.mockResolvedValue(false);
    const onClose = renderSection();

    await startDeletion(user);

    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Delete account',
      message: 'You will be signed out everywhere and your API keys will stop working. Your account is removed for good after 30 days unless you sign in before then.',
      confirmText: 'Delete my account', danger: true,
    });
    expect(mocks.api.post).not.toHaveBeenCalled();
    expect(mocks.logout).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText('Your password')).toHaveValue('my-secret');
    expect(screen.getByRole('button', { name: 'Delete My Account' })).toBeEnabled();
  });

  it('schedules confirmed deletion, shows the deadline, closes and signs out', async () => {
    const user = userEvent.setup();
    const deleteAfter = '2026-11-30T12:00:00Z';
    mocks.api.post.mockResolvedValue({ data: { delete_after: deleteAfter } });
    const onClose = renderSection();

    await startDeletion(user);

    await waitFor(() => expect(mocks.logout).toHaveBeenCalledOnce());
    expect(mocks.api.post).toHaveBeenCalledExactlyOnceWith('/auth/me/deletion', { password: 'my-secret' });
    const deadline = new Date(deleteAfter).toLocaleDateString(undefined, {
      day: 'numeric', month: 'long', year: 'numeric',
    });
    expect(mocks.toast.success).toHaveBeenCalledWith(
      `Your account will be deleted on ${deadline}. Sign in before then to keep it.`,
      { duration: 12000 }
    );
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('prevents repeated deletion requests while one is pending', async () => {
    const user = userEvent.setup();
    let resolveDeletion;
    mocks.api.post.mockReturnValue(new Promise((resolve) => { resolveDeletion = resolve; }));
    const onClose = renderSection();

    await startDeletion(user);
    expect(screen.getByRole('button', { name: 'Deleting...' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Deleting...' }));
    expect(mocks.api.post).toHaveBeenCalledOnce();
    expect(mocks.logout).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();

    await act(async () => resolveDeletion({ data: { delete_after: '2026-11-30T12:00:00Z' } }));
    expect(mocks.logout).toHaveBeenCalledOnce();
  });

  it.each([
    [{ response: { data: { detail: 'Account is unavailable.' } } }, 'Account is unavailable.'],
    [new Error('offline'), 'Could not check your account.'],
  ])('reports a preview failure and allows retry: %s', async (error, message) => {
    const user = userEvent.setup();
    mocks.api.get.mockRejectedValueOnce(error);
    renderSection();

    await user.click(screen.getByRole('button', { name: 'Delete Account' }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith(message));
    expect(screen.getByRole('button', { name: 'Delete Account' })).toBeEnabled();
    expect(screen.queryByPlaceholderText('Your password')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete Account' }));
    expect(await screen.findByPlaceholderText('Your password')).toBeInTheDocument();
  });

  it.each([
    [{ response: { data: { detail: 'Incorrect password.' } } }, 'Incorrect password.'],
    [new Error('offline'), 'Could not delete the account.'],
  ])('reports a deletion failure without signing out and allows retry: %s', async (error, message) => {
    const user = userEvent.setup();
    mocks.api.post.mockRejectedValueOnce(error).mockResolvedValue({
      data: { delete_after: '2026-11-30T12:00:00Z' },
    });
    const onClose = renderSection();

    await startDeletion(user);

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith(message));
    expect(mocks.logout).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(mocks.toast.success).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText('Your password')).toHaveValue('my-secret');
    await user.click(screen.getByRole('button', { name: 'Delete My Account' }));
    await waitFor(() => expect(mocks.logout).toHaveBeenCalledOnce());
    expect(mocks.api.post).toHaveBeenCalledTimes(2);
  });
});
