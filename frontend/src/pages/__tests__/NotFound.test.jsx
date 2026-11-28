/* Copyright 2017-present, The Visdom Authors */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from '../../App';

const mocks = vi.hoisted(() => ({ user: null, loading: false }));

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => mocks,
  api: { get: vi.fn(), post: vi.fn() },
}));

describe('NotFound', () => {
  it.each([
    [null, false, 'Back to home'],
    [{ id: 1 }, false, 'Open dashboard'],
    [null, true, null],
  ])('offers the right way back for the current session', (user, loading, destination) => {
    Object.assign(mocks, { user, loading });
    window.history.replaceState({}, '', '/typo');
    render(<App />);

    const article = within(screen.getByRole('article'));
    expect(article.getByRole('heading', { name: 'Page not found' })).toBeVisible();
    expect(article.getByText(/Nothing is served at/)).toHaveTextContent('/typo');
    if (destination) {
      expect(article.getByRole('link', { name: destination })).toHaveAttribute('href', '/');
    } else {
      expect(article.queryByRole('link')).toBeNull();
    }
  });
});
