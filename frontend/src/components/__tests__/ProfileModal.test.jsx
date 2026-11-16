/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProfileModal from '../ProfileModal';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
  setUser: vi.fn(),
  setAccessToken: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../context/AuthContext', () => ({
  api: mocks.api,
  useAuth: () => ({
    user: { id: 1, email: 'user@example.com', username: 'current_user' },
    setUser: mocks.setUser,
    setAccessToken: mocks.setAccessToken,
  }),
}));

vi.mock('../toast/useToast', () => ({
  useToast: () => mocks.toast,
}));

describe('ProfileModal - Username Availability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('displays error and allows retry when availability check fails (#58)', async () => {
    const user = userEvent.setup();
    mocks.api.get.mockRejectedValue(new Error('Network error'));

    render(<ProfileModal onClose={vi.fn()} />);

    const input = screen.getByDisplayValue('current_user');
    await user.clear(input);
    await user.type(input, 'new_user_name');

    // Should display error and retry button, NOT "Already taken"
    expect(await screen.findByText('Could not check availability.')).toBeInTheDocument();
    expect(screen.queryByText('Already taken')).not.toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: 'Retry' });
    expect(retryBtn).toBeInTheDocument();

    // Now mock retry to succeed
    mocks.api.get.mockResolvedValueOnce({ data: { available: true } });
    await user.click(retryBtn);

    expect(await screen.findByText('Available')).toBeInTheDocument();
    expect(screen.queryByText('Could not check availability.')).not.toBeInTheDocument();
  });
});
