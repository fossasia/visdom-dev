/* Copyright 2017-present, The Visdom Authors */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
  auth: { user: null, setUser: vi.fn(), setAccessToken: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../context/AuthContext', () => ({ api: mocks.api, useAuth: () => mocks.auth }));
vi.mock('../toast/useToast', () => ({ useToast: () => mocks.toast }));
vi.mock('../DeleteAccountSection', () => ({
  default: ({ onClose }) => (
    <button type="button" onClick={onClose}>Account deletion settings</button>
  ),
}));

import ProfileModal from '../ProfileModal';

const ACCOUNT = {
  username: 'alice', email: 'alice@example.org', tier: 'pro',
  created_at: '2025-01-15T12:00:00Z', last_login_at: '2026-10-20T12:00:00Z',
};

const renderProfile = () => {
  const onClose = vi.fn();
  render(<ProfileModal onClose={onClose} />);
  return onClose;
};

const enterUsername = async (user, value) => {
  await user.clear(screen.getByRole('textbox'));
  await user.type(screen.getByRole('textbox'), value);
};

const enterPasswords = async (user, password = 'new-secret', confirmation = password) => {
  await user.type(screen.getByLabelText('Current password'), 'old-secret');
  await user.type(screen.getByLabelText('New password', { exact: true }), password);
  await user.type(screen.getByLabelText('Confirm new password'), confirmation);
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.auth.user = { ...ACCOUNT };
  mocks.api.get.mockResolvedValue({ data: { available: true } });
});

afterEach(() => vi.useRealTimers());

describe('ProfileModal', () => {
  it('shows account details, username, password form and deletion settings', () => {
    renderProfile();

    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.getByText(ACCOUNT.email)).toBeInTheDocument();
    expect(screen.getByText('Pro', { exact: true })).toBeInTheDocument();
    expect(screen.getByText(new Date(ACCOUNT.created_at).toLocaleDateString(undefined, {
      year: 'numeric', month: 'long', day: 'numeric',
    }))).toBeInTheDocument();
    const lastLogin = new Date(ACCOUNT.last_login_at);
    expect(screen.getByText(`${lastLogin.toLocaleDateString()} at ${
      lastLogin.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }`)).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveValue('alice');
    expect(screen.getByRole('button', { name: 'Save Username' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Change Password' })).toBeDisabled();
    expect(screen.getByText('Account deletion settings')).toBeInTheDocument();
    expect(mocks.api.get).not.toHaveBeenCalled();
  });

  it('passes the close callback to the deletion section', async () => {
    const user = userEvent.setup();
    const onClose = renderProfile();

    await user.click(screen.getByRole('button', { name: 'Account deletion settings' }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('handles missing optional profile details', () => {
    mocks.auth.user = { username: 'alice', email: ACCOUNT.email };
    renderProfile();

    expect(screen.getByText('Free', { exact: true })).toBeInTheDocument();
    expect(screen.getByText('This is your first sign-in')).toBeInTheDocument();
    expect(screen.queryByText('Member since')).not.toBeInTheDocument();
  });

  it('closes with the close button', async () => {
    const user = userEvent.setup();
    const onClose = renderProfile();

    await user.click(document.querySelector('.gc-modal-close'));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('closes on the backdrop but keeps clicks inside the modal open', async () => {
    const user = userEvent.setup();
    const onClose = renderProfile();

    await user.click(screen.getByText('Profile'));
    expect(onClose).not.toHaveBeenCalled();
    await user.click(document.querySelector('.gc-modal-overlay'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  describe('username changes', () => {
    it.each(['ab', 'a'.repeat(31), 'bad!name'])('rejects invalid username %s without an API request', async (name) => {
      const user = userEvent.setup();
      renderProfile();

      await enterUsername(user, name);

      expect(screen.getByText('3-30 characters: letters, numbers, underscores, hyphens.')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Save Username' })).toBeDisabled();
      expect(mocks.api.get).not.toHaveBeenCalled();
    });

    it('debounces availability checks and cancels the check when unmounted', async () => {
      vi.useFakeTimers();
      const { unmount } = render(<ProfileModal onClose={vi.fn()} />);

      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'alice_new' } });
      expect(screen.getByText('Checking availability...')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Save Username' })).toBeDisabled();
      await act(() => vi.advanceTimersByTimeAsync(399));
      expect(mocks.api.get).not.toHaveBeenCalled();
      await act(() => vi.advanceTimersByTimeAsync(1));
      expect(mocks.api.get).toHaveBeenCalledExactlyOnceWith('/auth/username-availability', {
        params: { username: 'alice_new' },
      });
      expect(screen.getByText('Available')).toBeInTheDocument();

      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'another_name' } });
      unmount();
      await act(() => vi.advanceTimersByTimeAsync(400));
      expect(mocks.api.get).toHaveBeenCalledOnce();
    });

    it('keeps a taken username from being saved', async () => {
      const user = userEvent.setup();
      mocks.api.get.mockResolvedValue({ data: { available: false } });
      renderProfile();

      await enterUsername(user, 'taken_name');
      expect(await screen.findByText('Already taken')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Save Username' }));
      expect(mocks.api.patch).not.toHaveBeenCalled();
    });

    it('does not allow saving if the availability request fails', async () => {
      const user = userEvent.setup();
      mocks.api.get.mockRejectedValue(new Error('offline'));
      renderProfile();

      await enterUsername(user, 'alice_new');
      await waitFor(() => expect(screen.queryByText('Checking availability...')).not.toBeInTheDocument());

      expect(screen.getByRole('button', { name: 'Save Username' })).toBeDisabled();
      expect(mocks.api.patch).not.toHaveBeenCalled();
    });

    it('disables saving while the username update is pending', async () => {
      const user = userEvent.setup();
      let resolveSave;
      mocks.api.patch.mockReturnValue(new Promise((resolve) => { resolveSave = resolve; }));
      const onClose = renderProfile();

      await enterUsername(user, 'alice_new');
      await screen.findByText('Available');
      await user.click(screen.getByRole('button', { name: 'Save Username' }));
      expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
      await user.click(screen.getByRole('button', { name: 'Saving...' }));
      expect(mocks.api.patch).toHaveBeenCalledOnce();
      expect(onClose).not.toHaveBeenCalled();

      await act(async () => resolveSave({ data: { ...ACCOUNT, username: 'alice_new' } }));
      expect(onClose).toHaveBeenCalledOnce();
    });

    it('saves an available username, updates the signed-in user and closes', async () => {
      const user = userEvent.setup();
      const updated = { ...ACCOUNT, username: 'alice_new' };
      mocks.api.patch.mockResolvedValue({ data: updated });
      const onClose = renderProfile();

      await enterUsername(user, 'alice_new');
      await screen.findByText('Available');
      await user.click(screen.getByRole('button', { name: 'Save Username' }));

      await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
      expect(mocks.api.patch).toHaveBeenCalledExactlyOnceWith('/auth/me/username', { username: 'alice_new' });
      expect(mocks.auth.setUser).toHaveBeenCalledWith(updated);
      expect(mocks.toast.success).toHaveBeenCalledWith('Username updated.');
    });

    it.each([
      [{ response: { data: { detail: 'Username is already in use.' } } }, 'Username is already in use.'],
      [new Error('offline'), 'Failed to update username.'],
    ])('keeps the modal open after a save error: %s', async (error, message) => {
      const user = userEvent.setup();
      mocks.api.patch.mockRejectedValue(error);
      const onClose = renderProfile();

      await enterUsername(user, 'alice_new');
      await screen.findByText('Available');
      await user.click(screen.getByRole('button', { name: 'Save Username' }));

      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Save Username' })).toBeEnabled();
      expect(screen.getByRole('textbox')).toHaveValue('alice_new');
      expect(onClose).not.toHaveBeenCalled();
      expect(mocks.auth.setUser).not.toHaveBeenCalled();
    });
  });

  describe('password changes', () => {
    it.each([
      ['short', 'short', 'Password should have at least 6 characters.'],
      ['new-secret', 'different-secret', 'Passwords do not match.'],
    ])('rejects invalid passwords before contacting the API: %s', async (password, confirmation, message) => {
      const user = userEvent.setup();
      renderProfile();

      await enterPasswords(user, password, confirmation);
      await user.click(screen.getByRole('button', { name: 'Change Password' }));

      expect(mocks.toast.error).toHaveBeenCalledWith(message);
      expect(mocks.api.post).not.toHaveBeenCalled();
    });

    it('prevents duplicate password changes while the request is pending', async () => {
      const user = userEvent.setup();
      let resolveChange;
      mocks.api.post.mockReturnValue(new Promise((resolve) => { resolveChange = resolve; }));
      renderProfile();

      await enterPasswords(user);
      await user.click(screen.getByRole('button', { name: 'Change Password' }));
      expect(screen.getByRole('button', { name: 'Changing...' })).toBeDisabled();
      await user.click(screen.getByRole('button', { name: 'Changing...' }));
      expect(mocks.api.post).toHaveBeenCalledOnce();
      expect(mocks.auth.setAccessToken).not.toHaveBeenCalled();

      await act(async () => resolveChange({ data: { access_token: 'replacement-token' } }));
      expect(mocks.auth.setAccessToken).toHaveBeenCalledWith('replacement-token');
    });

    it('changes the password, replaces the token and clears the password fields', async () => {
      const user = userEvent.setup();
      mocks.api.post.mockResolvedValue({ data: { access_token: 'replacement-token' } });
      const onClose = renderProfile();

      await enterPasswords(user);
      await user.click(screen.getByRole('button', { name: 'Change Password' }));

      await waitFor(() => expect(mocks.toast.success).toHaveBeenCalledWith(
        'Password changed. Other devices have been signed out.'
      ));
      expect(mocks.api.post).toHaveBeenCalledExactlyOnceWith('/auth/change-password', {
        current_password: 'old-secret', new_password: 'new-secret',
      });
      expect(mocks.auth.setAccessToken).toHaveBeenCalledWith('replacement-token');
      expect(screen.getByLabelText('Current password')).toHaveValue('');
      expect(screen.getByLabelText('New password', { exact: true })).toHaveValue('');
      expect(screen.getByLabelText('Confirm new password')).toHaveValue('');
      expect(onClose).not.toHaveBeenCalled();
    });

    it.each([
      [{ response: { data: { detail: 'That is not your current password.' } } }, 'That is not your current password.'],
      [new Error('offline'), 'Could not change the password.'],
    ])('keeps the password fields after an API error: %s', async (error, message) => {
      const user = userEvent.setup();
      mocks.api.post.mockRejectedValue(error);
      renderProfile();

      await enterPasswords(user);
      await user.click(screen.getByRole('button', { name: 'Change Password' }));

      await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith(message));
      expect(screen.getByRole('button', { name: 'Change Password' })).toBeEnabled();
      expect(screen.getByLabelText('Current password')).toHaveValue('old-secret');
      expect(screen.getByLabelText('New password', { exact: true })).toHaveValue('new-secret');
      expect(screen.getByLabelText('Confirm new password')).toHaveValue('new-secret');
      expect(mocks.auth.setAccessToken).not.toHaveBeenCalled();
      expect(mocks.toast.success).not.toHaveBeenCalled();
    });
  });
});
