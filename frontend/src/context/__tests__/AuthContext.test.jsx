/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { AuthProvider, useAuth } from '../AuthContext';

vi.mock('axios', () => {
  const post = vi.fn();
  const get = vi.fn();
  const create = vi.fn(() => ({
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn(() => 0), eject: vi.fn() },
      response: { use: vi.fn(() => 0), eject: vi.fn() },
    },
  }));

  return {
    default: { post, get, create },
  };
});

vi.mock('../../utils/storage', () => ({
  clearAppStorage: vi.fn(),
}));

vi.mock('../../utils/requestCache', () => ({
  clearRequestCache: vi.fn(),
}));

const AuthStatus = () => {
  const { user, accessToken, loading, login, logout } = useAuth();

  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user ? user.email : 'none'}</span>
      <span data-testid="token">{accessToken || 'none'}</span>
      <button onClick={() => login('test@example.com', 'password123')}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  );
};

describe('AuthContext authentication state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderAuth = () =>
    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>
    );

  it('clears authentication state when refresh initialization fails', async () => {
    axios.post.mockRejectedValueOnce(new Error('No active session'));

    renderAuth();

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false');
    });

    expect(screen.getByTestId('user')).toHaveTextContent('none');
    expect(screen.getByTestId('token')).toHaveTextContent('none');
  });

  it('sets the user and access token after login succeeds', async () => {
    axios.post
      .mockRejectedValueOnce(new Error('No active session'))
      .mockResolvedValueOnce({ data: { access_token: 'test-token' } });

    axios.get.mockResolvedValueOnce({
      data: { email: 'test@example.com' },
    });

    renderAuth();

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false');
    });

    await act(async () => {
      screen.getByRole('button', { name: 'Login' }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
      expect(screen.getByTestId('token')).toHaveTextContent('test-token');
    });
  });

  it('clears user and token after logout', async () => {
    axios.post
      .mockResolvedValueOnce({ data: { access_token: 'initial-token' } })
      .mockResolvedValueOnce({ data: {} });

    axios.get.mockResolvedValueOnce({
      data: { email: 'test@example.com' },
    });

    renderAuth();

    await waitFor(() => {
      expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
    });

    await act(async () => {
      screen.getByRole('button', { name: 'Logout' }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('user')).toHaveTextContent('none');
      expect(screen.getByTestId('token')).toHaveTextContent('none');
    });
  });
});
