/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from '../../App';
import NotFound from '../NotFound';

const mocks = vi.hoisted(() => ({ user: null }));

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ user: mocks.user, loading: false }),
  api: { get: vi.fn(), post: vi.fn() },
}));

describe('NotFound', () => {
  it('names the missing page and links back to the console', () => {
    render(
      <MemoryRouter initialEntries={['/typo']}>
        <NotFound />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
    expect(screen.getByText(/Nothing is served at/)).toHaveTextContent('/typo');
    expect(screen.getByRole('link', { name: 'Back to the console' })).toHaveAttribute('href', '/');
  });

  it.each([
    ['signed out', null],
    ['signed in', { id: 1, email: 'test@example.com' }],
  ])('is what an unknown route renders, %s', (_label, user) => {
    mocks.user = user;
    window.history.pushState({}, '', '/typo');

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });
});
