/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Register from '../Register';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
  register: vi.fn(),
  login: vi.fn(),
  redirectAfterAuth: vi.fn(),
}));

vi.mock('../../context/AuthContext', () => ({
  api: mocks.api,
  useAuth: () => ({
    register: mocks.register,
    login: mocks.login,
  }),
}));

vi.mock('../../utils/helpers', () => ({
  resolvePostAuthTarget: () => '/',
  redirectAfterAuth: mocks.redirectAfterAuth,
}));

describe('Register Page - Username Availability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.api.get.mockImplementation((url) => {
      if (url === '/auth/generate-username') {
        return Promise.resolve({ data: { username: 'auto_user_1' } });
      }
      return Promise.resolve({ data: { available: true } });
    });
  });

  const renderRegister = () =>
    render(
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<Register />} />
        </Routes>
      </MemoryRouter>
    );

  it('reports "Available" when custom username check succeeds and is available', async () => {
    const user = userEvent.setup();
    mocks.api.get.mockImplementation((url) => {
      if (url === '/auth/generate-username') {
        return Promise.resolve({ data: { username: 'auto_user_1' } });
      }
      if (url === '/auth/username-availability') {
        return Promise.resolve({ data: { available: true } });
      }
      return Promise.reject(new Error('not found'));
    });

    renderRegister();

    await user.click(screen.getByRole('button', { name: 'Choose my own' }));
    const input = screen.getByPlaceholderText('your_username');
    await user.type(input, 'my_new_username');

    expect(await screen.findByText('Available')).toBeInTheDocument();
  });

  it('reports "Already taken" when custom username check succeeds and is taken', async () => {
    const user = userEvent.setup();
    mocks.api.get.mockImplementation((url) => {
      if (url === '/auth/generate-username') {
        return Promise.resolve({ data: { username: 'auto_user_1' } });
      }
      if (url === '/auth/username-availability') {
        return Promise.resolve({ data: { available: false } });
      }
      return Promise.reject(new Error('not found'));
    });

    renderRegister();

    await user.click(screen.getByRole('button', { name: 'Choose my own' }));
    const input = screen.getByPlaceholderText('your_username');
    await user.type(input, 'taken_user');

    expect(await screen.findByText('Already taken')).toBeInTheDocument();
  });

  it('reports "Could not check availability." and allows retry when request fails (#58)', async () => {
    const user = userEvent.setup();
    mocks.api.get.mockImplementation((url) => {
      if (url === '/auth/generate-username') {
        return Promise.resolve({ data: { username: 'auto_user_1' } });
      }
      if (url === '/auth/username-availability') {
        return Promise.reject(new Error('Network disconnected'));
      }
      return Promise.reject(new Error('not found'));
    });

    renderRegister();

    await user.click(screen.getByRole('button', { name: 'Choose my own' }));
    const input = screen.getByPlaceholderText('your_username');
    await user.type(input, 'abcdef11');

    // Should NOT report "Already taken" when the request fails
    expect(await screen.findByText('Could not check availability.')).toBeInTheDocument();
    expect(screen.queryByText('Already taken')).not.toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: 'Retry' });
    expect(retryBtn).toBeInTheDocument();

    // Now mock the next attempt to succeed
    mocks.api.get.mockImplementation((url) => {
      if (url === '/auth/username-availability') {
        return Promise.resolve({ data: { available: true } });
      }
      return Promise.resolve({ data: { username: 'auto_user_1' } });
    });

    await user.click(retryBtn);

    expect(await screen.findByText('Available')).toBeInTheDocument();
    expect(screen.queryByText('Could not check availability.')).not.toBeInTheDocument();
  });
});
