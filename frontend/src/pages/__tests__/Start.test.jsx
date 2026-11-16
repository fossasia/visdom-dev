/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../../App';

const mocks = vi.hoisted(() => ({ user: null }));

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ user: mocks.user, loading: false, login: vi.fn() }),
  api: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../Dashboard', () => ({
  default: () => <h1>Dashboard</h1>,
}));

const visit = (path, user = null) => {
  mocks.user = user;
  window.history.pushState({}, '', path);
  render(<App />);
};

describe('Start page', () => {
  afterEach(() => {
    mocks.user = null;
  });

  it('is what a signed-out visitor sees at the root', () => {
    visit('/');

    expect(screen.getByRole('heading', { level: 1, name: 'Watch training live, together.' })).toBeInTheDocument();
    for (const link of screen.getAllByRole('link', { name: 'Get started' })) {
      expect(link).toHaveAttribute('href', '/register');
    }
    for (const link of screen.getAllByRole('link', { name: 'Sign in' })) {
      expect(link).toHaveAttribute('href', '/login');
    }
  });

  it('shows the same client snippet as the Keys tab', () => {
    visit('/');

    expect(screen.getByText(/pip install "git\+https:\/\/github.com\/fossasia\/visdom.git@dev"/)).toBeInTheDocument();
    expect(screen.getByText(/workspace="your-workspace"/)).toBeInTheDocument();
  });

  it('still sends a signed-out link with a query to sign in', () => {
    visit('/?tab=billing');

    expect(screen.queryByRole('heading', { level: 1, name: 'Watch training live, together.' })).not.toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
  });

  it('leaves the dashboard at the root for a signed-in user', () => {
    visit('/', { id: 1, email: 'test@example.com' });

    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.queryByText('Watch training live, together.')).not.toBeInTheDocument();
  });
});
