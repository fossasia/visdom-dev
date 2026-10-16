
/* Copyright 2017-present, The Visdom Authors */

import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation, useNavigate, useNavigationType } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProtectedRoute } from '../ProtectedRoute';
import { useAuth } from '../../context/AuthContext';

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const LocationDisplay = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const navigationType = useNavigationType();

  return (
    <div>
      <div>Current path: {location.pathname}</div>
      <div>Navigation type: {navigationType}</div>
      <div data-testid="redirect-from">
        {location.state?.from || 'No redirect destination'}
      </div>
      <button onClick={() => navigate(-1)}>Back</button>
    </div>
  );
};

const renderProtectedRoute = () =>
  render(
    <MemoryRouter initialEntries={['/dashboard?tab=keys']}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <div>Protected dashboard</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>
  );

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading message while authentication is being checked', () => {
    useAuth.mockReturnValue({ user: null, loading: true });

    renderProtectedRoute();

    expect(screen.getByText('Checking Session...')).toBeInTheDocument();
    expect(screen.queryByText('Protected dashboard')).not.toBeInTheDocument();
  });

  it('redirects unauthenticated users to login and preserves the requested destination', () => {
    useAuth.mockReturnValue({ user: null, loading: false });

    renderProtectedRoute();

    expect(screen.getByText('Current path: /login')).toBeInTheDocument();
    expect(screen.getByTestId('redirect-from')).toHaveTextContent('/dashboard?tab=keys');
  });

  it('uses history replacement when redirecting unauthenticated users to login', () => {
    useAuth.mockReturnValue({ user: null, loading: false });

    renderProtectedRoute();

    expect(screen.getByText('Navigation type: REPLACE')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));

    expect(screen.getByText('Current path: /login')).toBeInTheDocument();
    expect(screen.queryByText('Protected dashboard')).not.toBeInTheDocument();
  });

  it('renders protected content for authenticated users', () => {
    useAuth.mockReturnValue({
      user: { id: 1, email: 'test@example.com' },
      loading: false,
    });

    renderProtectedRoute();

    expect(screen.getByText('Protected dashboard')).toBeInTheDocument();
  });
});

