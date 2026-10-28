/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ForgotPassword from '../ForgotPassword';

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

describe('ForgotPassword', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.api.post.mockReset();
    mocks.toast.error.mockReset();
    mocks.toast.success.mockReset();
  });

  const renderForgotPassword = (initialEntry = '/forgot-password') =>
    render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>
    );

  describe('UI rendering', () => {
    it('renders the initial forgot password form with email input, submit button, and sign in link', () => {
      renderForgotPassword();

      expect(screen.getByText('Reset your password')).toBeInTheDocument();
      expect(
        screen.getByText('Enter the email you signed up with and we will send you a link to choose a new password.')
      ).toBeInTheDocument();
      expect(screen.getByLabelText('Email Address')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Send reset link' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
    });

    it('pre-fills the email field when email is provided in location state', () => {
      renderForgotPassword({
        pathname: '/forgot-password',
        state: { email: 'prefilled@example.com' },
      });

      expect(screen.getByPlaceholderText('you@example.com')).toHaveValue('prefilled@example.com');
    });
  });

  describe('form submission and button actions', () => {
    it('submits trimmed email and displays the inbox confirmation screen when email sending is enabled', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockResolvedValueOnce({
        data: { email_enabled: true },
      });

      renderForgotPassword();

      await user.type(screen.getByPlaceholderText('you@example.com'), '  user@example.com  ');
      await user.click(screen.getByRole('button', { name: 'Send reset link' }));

      await waitFor(() => {
        expect(mocks.api.post).toHaveBeenCalledWith('/auth/forgot-password', {
          email: 'user@example.com',
        });
      });

      expect(await screen.findByText('Check your inbox')).toBeInTheDocument();
      expect(screen.getByText('user@example.com')).toBeInTheDocument();
      expect(
        screen.getByText(/has an account, a link to choose a new password is on its way/)
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Send another' })).toBeInTheDocument();
    });

    it('returns to the form when clicking "Send another" on the inbox confirmation screen', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockResolvedValueOnce({
        data: { email_enabled: true },
      });

      renderForgotPassword();

      await user.type(screen.getByPlaceholderText('you@example.com'), 'user@example.com');
      await user.click(screen.getByRole('button', { name: 'Send reset link' }));

      const sendAnotherBtn = await screen.findByRole('button', { name: 'Send another' });
      await user.click(sendAnotherBtn);

      expect(screen.getByRole('button', { name: 'Send reset link' })).toBeInTheDocument();
      expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument();
    });

    it('shows contact support link on the inbox screen when support_contact is provided', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockResolvedValueOnce({
        data: { email_enabled: true, support_contact: 'support@example.com' },
      });

      renderForgotPassword();

      await user.type(screen.getByPlaceholderText('you@example.com'), 'user@example.com');
      await user.click(screen.getByRole('button', { name: 'Send reset link' }));

      const supportLink = await screen.findByRole('link', { name: 'contact support' });
      expect(supportLink).toHaveAttribute('href', 'mailto:support@example.com?subject=Password%20reset');
    });

    it('shows email disabled notice with contact support link when server cannot send email', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockResolvedValueOnce({
        data: { email_enabled: false, support_contact: 'https://support.example.com' },
      });

      renderForgotPassword();

      await user.type(screen.getByPlaceholderText('you@example.com'), 'user@example.com');
      await user.click(screen.getByRole('button', { name: 'Send reset link' }));

      expect(
        await screen.findByText(/This server cannot send email yet, so a reset link cannot be sent\./)
      ).toBeInTheDocument();
      const supportLink = screen.getByRole('link', { name: 'Contact support' });
      expect(supportLink).toHaveAttribute('href', 'https://support.example.com');
    });

    it('shows fallback text when email is disabled and no support contact is provided', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockResolvedValueOnce({
        data: { email_enabled: false, support_contact: null },
      });

      renderForgotPassword();

      await user.type(screen.getByPlaceholderText('you@example.com'), 'user@example.com');
      await user.click(screen.getByRole('button', { name: 'Send reset link' }));

      expect(
        await screen.findByText(/Ask whoever runs this server/)
      ).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: /contact support/i })).not.toBeInTheDocument();
    });
  });

  describe('API error handling', () => {
    it('shows error toast with the backend error detail when API request fails', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockRejectedValueOnce({
        response: { data: { detail: 'Too many requests. Please try again later.' } },
      });

      renderForgotPassword();

      await user.type(screen.getByPlaceholderText('you@example.com'), 'user@example.com');
      await user.click(screen.getByRole('button', { name: 'Send reset link' }));

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith('Too many requests. Please try again later.');
      });

      // Submit button should be re-enabled and form should remain visible
      const submitBtn = screen.getByRole('button', { name: 'Send reset link' });
      expect(submitBtn).toBeEnabled();
    });

    it('shows fallback error toast when API error response has no detail', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockRejectedValueOnce(new Error('Network error'));

      renderForgotPassword();

      await user.type(screen.getByPlaceholderText('you@example.com'), 'user@example.com');
      await user.click(screen.getByRole('button', { name: 'Send reset link' }));

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith('Could not send a reset link. Try again in a moment.');
      });
    });

    it('shows error toast with joined message items when detail is an array', async () => {
      const user = userEvent.setup({ delay: null });
      mocks.api.post.mockRejectedValueOnce({
        response: {
          data: {
            detail: [{ msg: 'Enter a valid email address' }],
          },
        },
      });

      renderForgotPassword();

      await user.type(screen.getByPlaceholderText('you@example.com'), 'notfound@example.com');
      await user.click(screen.getByRole('button', { name: 'Send reset link' }));

      await waitFor(() => {
        expect(mocks.toast.error).toHaveBeenCalledWith('Enter a valid email address');
      });
    });
  });
});
