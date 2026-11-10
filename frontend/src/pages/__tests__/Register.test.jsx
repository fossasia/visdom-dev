/* Copyright 2017-present, The Visdom Authors */

import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn() },
  register: vi.fn(),
  login: vi.fn(),
}));

vi.mock('../../context/AuthContext', () => ({
  api: mocks.api,
  useAuth: () => ({ register: mocks.register, login: mocks.login }),
}));

import Register from '../Register';

let requests;

const deferred = () => {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  requests = new Map();
  mocks.api.get.mockImplementation((path, config) => {
    if (path === '/auth/generate-username') {
      return Promise.resolve({ data: { username: 'suggested_name' } });
    }

    const request = deferred();
    requests.set(config.params.username, request);
    return request.promise;
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('Register', () => {
  it('does not let a stale availability response replace the latest result', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    await user.click(screen.getByRole('button', { name: 'Choose my own' }));
    const usernameInput = screen.getByPlaceholderText('your_username');
    await user.type(usernameInput, 'older_name');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    await user.clear(usernameInput);
    await user.type(usernameInput, 'latest_name');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    await act(async () => {
      requests.get('latest_name').resolve({ data: { available: true } });
      await requests.get('latest_name').promise;
    });
    expect(screen.getByText('Available')).toBeInTheDocument();

    await act(async () => {
      requests.get('older_name').resolve({ data: { available: false } });
      await requests.get('older_name').promise;
    });

    expect(screen.getByText('Available')).toBeInTheDocument();
  });
});
