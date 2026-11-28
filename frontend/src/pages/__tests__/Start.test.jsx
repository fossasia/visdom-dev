/* Copyright 2017-present, The Visdom Authors */

import { render, screen, within } from '@testing-library/react';
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

  it('shows one Visdom logo and links it home from the header', () => {
    visit('/');
    const home = screen.getByRole('link', { name: 'Visdom home' });
    const logos = document.querySelectorAll('img[src="/logo.svg"]');
    expect(logos).toHaveLength(1);
    expect(home).toContainElement(logos[0]);
    expect(home).toHaveAttribute('href', '/');
  });

  it('introduces the open source projects with text and repository links', () => {
    visit('/');
    const section = within(screen.getByRole('region', { name: 'Built in the open' }));
    expect(section.queryByRole('img')).toBeNull();
    const operator = section.getByRole('link', { name: 'FOSSASIA' });
    expect(operator).toHaveAttribute('href', 'https://fossasia.org');
    expect(operator).toHaveAttribute('rel', 'noopener');
    expect(operator.closest('p')).toHaveTextContent('Visdom is open source and run by FOSSASIA.');
    for (const project of ['fossasia/visdom', 'fossasia/visdom-dev']) {
      expect(section.getByRole('link', { name: project })).toHaveAttribute('href', `https://github.com/${project}`);
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
