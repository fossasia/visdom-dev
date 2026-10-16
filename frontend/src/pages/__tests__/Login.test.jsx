/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Login from '../Login';

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  redirectAfterAuth: vi.fn(),
}));

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ login: mocks.login }),
}));

vi.mock('../../utils/helpers', () => ({
  resolvePostAuthTarget: () => '/',
  redirectAfterAuth: mocks.redirectAfterAuth,
}));

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderLogin = () =>
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<Login />} />
        </Routes>
      </MemoryRouter>
    );

  it('logs in successfully and redirects after authentication', async () => {
    const user = userEvent.setup();
    mocks.login.mockResolvedValue({ id: 1, email: 'test@example.com' });

    renderLogin();

    await user.type(screen.getByPlaceholderText('you@example.com'), 'test@example.com');
    await user.type(screen.getByPlaceholderText('••••••••'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Sign In' }));

    await waitFor(() => {
      expect(mocks.login).toHaveBeenCalledWith('test@example.com', 'password123');
      expect(mocks.redirectAfterAuth).toHaveBeenCalled();
    });
  });

  it('shows an error when login fails', async () => {
    const user = userEvent.setup();
    mocks.login.mockRejectedValue(new Error('Invalid credentials'));

    renderLogin();

    await user.type(screen.getByPlaceholderText('you@example.com'), 'test@example.com');
    await user.type(screen.getByPlaceholderText('••••••••'), 'wrongpass');
    await user.click(screen.getByRole('button', { name: 'Sign In' }));

    expect(
      await screen.findByText('Login failed. Please check your credentials.')
    ).toBeInTheDocument();
  });
});

