/* Copyright 2017-present, The Visdom Authors */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import App from '../../App';

const session = vi.hoisted(() => ({ user: null, loading: false }));
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => session,
  api: { get: vi.fn(async () => ({ data: { username: 'ana' } })) },
}));

beforeEach(() => { session.user = null; });

it('takes visitors to the new heading from the footer and preserves Back scrolling', async () => {
  window.history.replaceState({}, '', '/');
  const user = userEvent.setup();
  render(<App />);
  document.documentElement.scrollTop = 800;
  await user.click(within(screen.getByRole('contentinfo')).getByRole('link', { name: 'Privacy' }));
  expect(screen.getByRole('heading', { name: 'Privacy' })).toHaveFocus();
  expect(document.documentElement.scrollTop).toBe(0);
  document.documentElement.scrollTop = 325;
  window.history.back();
  await waitFor(() => expect(window.location.pathname).toBe('/'));
  expect(document.documentElement.scrollTop).toBe(325);
});

it('names the password and account fields on sign-in and registration', async () => {
  window.history.replaceState({}, '', '/login');
  const user = userEvent.setup();
  render(<App />);
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  expect(screen.getByLabelText('Email Address')).toHaveAttribute('type', 'email');
  await user.click(screen.getByRole('link', { name: 'Sign up' }));
  expect(screen.getByRole('heading', { level: 1, name: 'Create your user account' })).toHaveFocus();
  expect(screen.getByLabelText('Confirm Password')).toHaveAttribute('type', 'password');
  await user.click(screen.getByRole('button', { name: 'Choose my own' }));
  expect(screen.getByLabelText('Username')).toHaveAttribute('type', 'text');
});

it.each([
  [null, 'Sign in', '/login?plan=pro'],
  [{ id: 1 }, 'Open dashboard', '/'],
])('returns from Privacy through the header and keeps the sign-in destination', async (account, label, path) => {
  session.user = account;
  window.history.replaceState({ usr: { from: '/share/join' } }, '', '/privacy?plan=pro');
  render(<App />);
  const article = within(screen.getByRole('article'));
  expect(article.queryByRole('link', { name: /back to sign in|open dashboard/i })).toBeNull();
  const link = within(screen.getByRole('banner')).getByRole('link', { name: label });
  expect(link).toHaveAttribute('href', path);
  if (!account) {
    await userEvent.click(link);
    expect(window.history.state.usr.from).toBe('/share/join');
  }
});
