/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import ProfileModal from '../ProfileModal';

// Mock AuthContext
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u-1', username: 'alice', email: 'alice@example.com', tier: 'free' },
    setUser: vi.fn(),
    setAccessToken: vi.fn(),
  }),
  api: {
    get: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
  },
}));

// Mock ConfirmContext
vi.mock('../../context/ConfirmContext', () => ({
  useConfirm: () => vi.fn(),
}));

// Mock toast
vi.mock('../toast/useToast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

describe('ProfileModal Accessibility', () => {
  it('has role="dialog", accessible name "Profile", and close button', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(<ProfileModal onClose={handleClose} />);

    const dialog = screen.getByRole('dialog', { name: 'Profile' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    // Close button has accessible name "Close"
    const closeBtn = screen.getByRole('button', { name: 'Close' });
    expect(closeBtn).toBeInTheDocument();

    // Escape closes the modal
    await user.keyboard('{Escape}');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});

