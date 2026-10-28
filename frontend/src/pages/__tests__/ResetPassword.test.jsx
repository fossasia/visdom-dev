/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation, useNavigationType } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ResetPassword from '../ResetPassword';

const mocks = vi.hoisted(() => ({
  api: { post: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('../../context/AuthContext', () => ({
  api: mocks.api,
}));

vi.mock('../../components/toast/useToast', () => ({
  useToast: () => mocks.toast,
}));

const LocationDisplay = () => {
  const location = useLocation();
  const navigationType = useNavigationType();
  return (
    <div>
      <div>Current path: {location.pathname}</div>
      <div>Navigation type: {navigationType}</div>
    </div>
  );
};

describe('ResetPassword', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.api.post.mockReset();
    mocks.toast.error.mockReset();
    mocks.toast.success.mockReset();
  });

  const renderResetPassword = (initialEntry = '/reset-password#token=valid-token-123') =>
    render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/login" element={<LocationDisplay />} />
          <Route path="/forgot-password" element={<div>Forgot Password Page</div>} />
        </Routes>
      </MemoryRouter>
    );

  describe('UI rendering', () => {
    it('shows invalid/expired link screen when no token is present in the hash', () => {
      renderResetPassword('/reset-password');

      expect(screen.getByText('Reset your password')).toBeInTheDocument();
      expect(
        screen.getByText(
          'This reset link is invalid or has expired. Links work once, for an hour after they are sent.'
        )
      ).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Ask for a new link' })).toHaveAttribute(
        'href',
        '/forgot-password'
      );
      expect(screen.queryByLabelText('New Password')).not.toBeInTheDocument();
    });

    it('renders the password reset form when a valid token is present in the URL hash', () => {
      renderResetPassword('/reset-password#token=valid-token-123');

      expect(screen.getByText('Choose a new password')).toBeInTheDocument();
      expect(screen.getByLabelText('New Password')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Minimum 6 characters')).toBeInTheDocument();
      expect(screen.getByLabelText('Confirm Password')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Re-enter password')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Set new password' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/login');
    });
  });

  describe('validation and button actions', () => {
    it('shows error toast when password has fewer than 6 characters and does not call API', async () => {
      const user = userEvent.setup({ delay: null });
      renderResetPassword();

      await user.type(screen.getByPlaceholderText('Minimum 6 characters'), '12345');
      await user.type(screen.getByPlaceholderText('Re-enter password'), '12345');
      await user.click(screen.getByRole('button', { name: 'Set new password' }));

      expect(mocks.toast.error).toHaveBeenCalledWith('Password should have at least 6 characters.');
      expect(mocks.api.post).not.toHaveBeenCalled();
    });

    it('shows error toast when passwords do not match and does not call API', async () => {
      const user = userEvent.setup({ delay: null });
      renderResetPassword();

      await user.type(screen.getByPlaceholderText('Minimum 6 characters'), 'pass123');
      await user.type(screen.getByPlaceholderText('Re-enter password'), 'diff123');
      await user.click(screen.getByRole('button', { name: 'Set new password' }));

      expect(mocks.toast.error).toHaveBeenCalledWith('Passwords do not match.');
      expect(mocks.api.post).not.toHaveBeenCalled();
    });

    it('submits valid password with token, shows success toast, and navigates to login with replace', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockResolvedValueOnce({
        data: { detail: 'Password reset successful!' },
      });

      renderResetPassword('/reset-password#token=valid-token-123');

      await user.type(screen.getByPlaceholderText('Minimum 6 characters'), 'secret123');
      await user.type(screen.getByPlaceholderText('Re-enter password'), 'secret123');
      await user.click(screen.getByRole('button', { name: 'Set new password' }));

      await waitFor(() => {
        expect(mocks.api.post).toHaveBeenCalledWith('/auth/reset-password', {
          token: 'valid-token-123',
          password: 'secret123',
        });
        expect(mocks.toast.success).toHaveBeenCalledWith('Password reset successful!');
      });

      expect(await screen.findByText('Current path: /login')).toBeInTheDocument();
      expect(screen.getByText('Navigation type: REPLACE')).toBeInTheDocument();
    });

    it('shows fallback success toast when server response does not contain detail', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockResolvedValueOnce({
        data: {},
      });

      renderResetPassword('/reset-password#token=valid-token-123');

      await user.type(screen.getByPlaceholderText('Minimum 6 characters'), 'secret123');
      await user.type(screen.getByPlaceholderText('Re-enter password'), 'secret123');
      await user.click(screen.getByRole('button', { name: 'Set new password' }));

      await waitFor(() => {
        expect(mocks.toast.success).toHaveBeenCalledWith('Your password has been changed.');
      });
    });

    it('toggles password visibility when the show/hide password button is clicked', async () => {
      const user = userEvent.setup({ delay: null });
      renderResetPassword();

      const newPasswordInput = screen.getByPlaceholderText('Minimum 6 characters');
      expect(newPasswordInput).toHaveAttribute('type', 'password');

      const toggleButtons = screen.getAllByRole('button', { name: 'Show password' });
      await user.click(toggleButtons[0]);

      expect(newPasswordInput).toHaveAttribute('type', 'text');

      const hideButton = screen.getByRole('button', { name: 'Hide password' });
      await user.click(hideButton);

      expect(newPasswordInput).toHaveAttribute('type', 'password');
    });
  });

  describe('API error handling', () => {
    it('switches to invalid/expired screen and displays error toast when API returns status 400', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockRejectedValueOnce({
        response: {
          status: 400,
          data: { detail: 'This reset token has expired or is invalid.' },
        },
      });

      renderResetPassword('/reset-password#token=expired-token');

      await user.type(screen.getByPlaceholderText('Minimum 6 characters'), 'secret123');
      await user.type(screen.getByPlaceholderText('Re-enter password'), 'secret123');
      await user.click(screen.getByRole('button', { name: 'Set new password' }));

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith('This reset token has expired or is invalid.');
      });

      expect(
        await screen.findByText(
          'This reset link is invalid or has expired. Links work once, for an hour after they are sent.'
        )
      ).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Ask for a new link' })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Set new password' })).not.toBeInTheDocument();
    });

    it('keeps the form visible and re-enables submit button when API returns a non-400 error', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockRejectedValueOnce({
        response: {
          status: 500,
          data: { detail: 'Internal server error. Please try again.' },
        },
      });

      renderResetPassword('/reset-password#token=valid-token');

      await user.type(screen.getByPlaceholderText('Minimum 6 characters'), 'secret123');
      await user.type(screen.getByPlaceholderText('Re-enter password'), 'secret123');
      await user.click(screen.getByRole('button', { name: 'Set new password' }));

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith('Internal server error. Please try again.');
      });

      const submitBtn = screen.getByRole('button', { name: 'Set new password' });
      expect(submitBtn).toBeInTheDocument();
      expect(submitBtn).toBeEnabled();
    });

    it('shows fallback error toast when API error response contains no detail', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockRejectedValueOnce(new Error('Network error'));

      renderResetPassword('/reset-password#token=valid-token');

      await user.type(screen.getByPlaceholderText('Minimum 6 characters'), 'secret123');
      await user.type(screen.getByPlaceholderText('Re-enter password'), 'secret123');
      await user.click(screen.getByRole('button', { name: 'Set new password' }));

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith(
          'Could not change the password. Try again in a moment.'
        );
      });
    });
  });
});
