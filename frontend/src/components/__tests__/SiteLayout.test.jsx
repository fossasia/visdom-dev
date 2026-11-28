/* Copyright 2017-present, The Visdom Authors */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import SiteLayout from '../SiteLayout';

const session = vi.hoisted(() => ({ user: null, loading: false }));
vi.mock('../../context/AuthContext', () => ({ useAuth: () => session }));
beforeEach(() => { Object.assign(session, { user: null, loading: false }); });

function mount() {
  render(<MemoryRouter><SiteLayout><main>Page</main></SiteLayout></MemoryRouter>);
}

it('links home from the header and groups public destinations in the footer', () => {
  mount();
  expect(within(screen.getByRole('banner')).getByRole('link', { name: 'Visdom home' })).toHaveAttribute('href', '/');
  const footer = within(screen.getByRole('contentinfo'));
  for (const [name, path] of [['Quickstart', 'https://github.com/fossasia/visdom-dev/blob/main/TESTER_QUICKSTART.md'], ['Privacy', '/privacy'], ['Cookies', '/cookies'], ['Contact us', 'mailto:office@fossasia.org']]) {
    expect(footer.getByRole('link', { name })).toHaveAttribute('href', path);
  }
  expect(footer.getAllByRole('heading').map(heading => heading.textContent)).toEqual(['Product', 'Open source', 'Legal']);
  expect(within(footer.getByRole('heading', { name: 'Product' }).parentElement).getByRole('link', { name: 'Contact us' })).toBeVisible();
  expect(screen.getByRole('contentinfo')).toHaveTextContent('visdom.dev is run by FOSSASIA PTE. LTD., Singapore.');
  for (const name of ['FOSSASIA PTE. LTD.', `© ${new Date().getFullYear()} FOSSASIA`]) {
    const link = footer.getByRole('link', { name });
    expect(link).toHaveAttribute('href', 'https://fossasia.org');
    expect(link).toHaveAttribute('rel', 'noopener');
  }
});

it('shows a single named footer image with plots clipped to the same letters as its flat fallback', () => {
  mount();
  const footer = within(screen.getByRole('contentinfo'));
  const wordmark = footer.getByRole('img', { name: 'visdom' });
  expect(wordmark).toHaveAttribute('focusable', 'false');
  expect(wordmark.querySelector('a, button, [tabindex], animate, animateTransform')).toBeNull();
  const letters = wordmark.querySelector('text');
  expect(letters).toHaveTextContent(/^visdom$/);
  expect(wordmark.querySelector('clipPath use')).toHaveAttribute('href', `#${letters.id}`);
  const artwork = wordmark.querySelector('[clip-path]');
  expect(artwork).toHaveAttribute('clip-path', `url(#${wordmark.querySelector('clipPath').id})`);
  expect(artwork.closest('[aria-hidden="true"]')).toBeInTheDocument();
  expect(artwork).toHaveAttribute('display', 'none');
  expect(artwork.previousElementSibling).toBe(letters);
  expect(artwork.querySelectorAll('polyline')).toHaveLength(3);
  expect(artwork.querySelectorAll('rect[fill-opacity]')).toHaveLength(64);
  expect(artwork.querySelectorAll('path[stroke-linecap="round"]')).toHaveLength(6);
});

it.each([
  [null, 'Get started', '/register'],
  [{ id: 1 }, 'Open dashboard', '/'],
])('uses the current session for navigation and restores focus after the menu closes', async (account, action, path) => {
  session.user = account;
  mount();
  const header = within(screen.getByRole('banner'));
  const footer = within(screen.getByRole('contentinfo'));
  for (const region of [header, footer]) {
    expect(region.getByRole('link', { name: action })).toHaveAttribute('href', path);
    if (account) {
      expect(region.queryByRole('link', { name: 'Sign in' })).toBeNull();
      expect(region.queryByRole('link', { name: 'Get started' })).toBeNull();
    } else {
      expect(region.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
      expect(region.queryByRole('link', { name: 'Open dashboard' })).toBeNull();
    }
  }
  const user = userEvent.setup();
  const trigger = screen.getByRole('button', { name: 'Menu' });
  const panel = document.querySelector('dialog');
  panel.showModal = () => { panel.open = true; };
  panel.close = () => {
    panel.open = false;
    panel.dispatchEvent(new Event('close'));
  };
  await user.click(trigger);
  const dialog = screen.getByRole('dialog');
  const close = within(dialog).getByRole('button', { name: 'Close menu' });
  close.focus();
  await user.tab({ shift: true });
  const destination = within(dialog).getByRole('link', { name: action });
  expect(destination).toHaveAttribute('href', path);
  expect(destination).toHaveFocus();
  await user.tab();
  expect(close).toHaveFocus();
  await user.click(close);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(trigger).toHaveFocus();
});

it('keeps public links available while the session is being checked', () => {
  session.loading = true;
  mount();
  expect(screen.getAllByRole('link', { name: 'Quickstart' })).toHaveLength(2);
  for (const name of ['Sign in', 'Get started', 'Open dashboard']) {
    expect(screen.queryByRole('link', { name })).toBeNull();
  }
});
