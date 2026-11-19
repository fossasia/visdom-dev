/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BillingTab from '../BillingTab';
import { clearRequestCache } from '../../../utils/requestCache';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn() },
  user: { id: 'u-1', email: 'test@example.com', tier: 'free' },
  setUser: vi.fn(),
}));

vi.mock('../../../context/AuthContext', () => ({
  api: mocks.api,
  useAuth: () => ({ user: mocks.user, setUser: mocks.setUser }),
}));

vi.mock('../../toast/useToast', () => ({
  useToast: () => mocks.toast,
}));

vi.mock('../CheckoutModal', () => ({
  default: ({ plan, onClose, onComplete }) => (
    <div data-testid="checkout-modal">
      <span>Modal for {plan.name}</span>
      <button onClick={onClose} type="button">
        Close Checkout
      </button>
      <button onClick={() => onComplete('sess_123')} type="button">
        Complete Payment
      </button>
    </div>
  ),
}));

describe('BillingTab', () => {
  const plans = [
    {
      id: 'free',
      name: 'Free',
      price: 0,
      checkout: false,
      features: ['1 workspace', '1 seat', '10 API keys'],
    },
    {
      id: 'pro',
      name: 'Pro',
      price: 20,
      checkout: true,
      features: ['5 workspaces', '5 seats', 'Unlimited API keys', '5 GB storage'],
    },
    {
      id: 'enterprise',
      name: 'Enterprise',
      price: null,
      checkout: false,
      features: ['Unlimited workspaces', 'Dedicated support'],
    },
  ];

  const subscription = {
    tier: 'free',
    plan: { id: 'free', name: 'Free' },
    billing: {
      status: null,
      can_manage: false,
    },
    support_contact: 'support@example.com',
    usage: {
      workspaces: { used: 1, limit: 1 },
      members: { used: 1, limit: 1 },
      api_keys: { used: 3, limit: 10 },
      storage: { used: 104857600, limit: 1073741824 }, // 100 MB / 1.0 GB
    },
  };

  const originalLocation = window.location;

  beforeEach(() => {
    vi.clearAllMocks();
    clearRequestCache();
    mocks.user = { id: 'u-1', email: 'test@example.com', tier: 'free' };
    mocks.api.get.mockImplementation((url) => {
      if (url === '/billing/plans') return Promise.resolve({ data: plans });
      if (url === '/billing/subscription') return Promise.resolve({ data: subscription });
      return Promise.reject(new Error(`Unhandled GET: ${url}`));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.location = originalLocation;
  });

  describe('loading state', () => {
    it('shows loading panel while data is fetching', () => {
      mocks.api.get.mockReturnValue(new Promise(() => {}));
      render(<BillingTab />);

      expect(screen.getByText('Loading billing information...')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('displays error details when fetching fails with API message', async () => {
      mocks.api.get.mockRejectedValue({
        response: { data: { detail: 'Billing service is currently down.' } },
      });
      render(<BillingTab />);

      expect(await screen.findByText('Billing service is currently down.')).toBeInTheDocument();
    });

    it('displays fallback error message when request fails without detail', async () => {
      mocks.api.get.mockRejectedValue(new Error('Network error'));
      render(<BillingTab />);

      expect(await screen.findByText('Failed to load billing information.')).toBeInTheDocument();
    });
  });

  describe('plans and subscription display', () => {
    it('renders all plans with price, features, and active badge', async () => {
      render(<BillingTab />);

      expect(await screen.findByText('Subscription Plans')).toBeInTheDocument();
      expect(screen.getByText('Free')).toBeInTheDocument();
      expect(screen.getByText('$0')).toBeInTheDocument();
      expect(screen.getByText('Current Plan', { selector: '.gc-current-pill' })).toBeInTheDocument();

      expect(screen.getByText('Pro')).toBeInTheDocument();
      expect(screen.getByText('$20')).toBeInTheDocument();

      expect(screen.getByText('Enterprise')).toBeInTheDocument();
      expect(screen.getByText('Custom')).toBeInTheDocument();

      expect(screen.getByText('1 workspace')).toBeInTheDocument();
      expect(screen.getByText('5 GB storage')).toBeInTheDocument();
      expect(screen.getByText('Dedicated support')).toBeInTheDocument();
    });

    it('renders cycle usage metrics with proper units and limits', async () => {
      render(<BillingTab />);

      expect(await screen.findByText('Usage This Cycle')).toBeInTheDocument();
      expect(screen.getByText('Workspaces')).toBeInTheDocument();
      expect(screen.getByText('Team seats')).toBeInTheDocument();
      expect(screen.getAllByText('1 / 1')).toHaveLength(2);

      expect(screen.getByText('API keys')).toBeInTheDocument();
      expect(screen.getByText('3 / 10')).toBeInTheDocument();

      expect(screen.getByText('Storage')).toBeInTheDocument();
      expect(screen.getByText('100 MB / 1.0 GB')).toBeInTheDocument();
    });

    it('highlights exceeded usage in danger text', async () => {
      mocks.api.get.mockImplementation((url) => {
        if (url === '/billing/plans') return Promise.resolve({ data: plans });
        if (url === '/billing/subscription') {
          return Promise.resolve({
            data: {
              ...subscription,
              usage: {
                workspaces: { used: 3, limit: 1 }, // exceeded
                members: { used: 1, limit: 1 },
                api_keys: { used: 5, limit: null }, // unlimited
              },
            },
          });
        }
        return Promise.reject(new Error(`Unhandled GET: ${url}`));
      });

      render(<BillingTab />);

      expect(await screen.findByText('Usage This Cycle')).toBeInTheDocument();
      const workspacesCount = screen.getByText('3 / 1');
      expect(workspacesCount).toHaveClass('gc-text-danger');

      expect(screen.getByText('5 / Unlimited')).toBeInTheDocument();
    });

    it('shows contact button for enterprise/custom plan', async () => {
      render(<BillingTab />);

      const enterpriseCard = (await screen.findByText('Enterprise')).closest('.gc-price-card');
      const contactBtn = within(enterpriseCard).getByRole('link', { name: 'Contact us' });
      expect(contactBtn).toHaveAttribute('href', expect.stringContaining('mailto:support@example.com'));
    });

    it('renders subscription notes when paying', async () => {
      mocks.api.get.mockImplementation((url) => {
        if (url === '/billing/plans') return Promise.resolve({ data: plans });
        if (url === '/billing/subscription') {
          return Promise.resolve({
            data: {
              ...subscription,
              tier: 'pro',
              plan: { id: 'pro', name: 'Pro' },
              billing: {
                status: 'active',
                can_manage: true,
                renews_at: '2026-12-01T00:00:00Z',
              },
            },
          });
        }
        return Promise.reject(new Error(`Unhandled GET: ${url}`));
      });

      render(<BillingTab />);

      expect(
        await screen.findByText(/Your Pro plan renews on 1 December 2026\./)
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Manage billing' })).toBeInTheDocument();
    });

    it('renders past-due warning note when billing is past due', async () => {
      mocks.api.get.mockImplementation((url) => {
        if (url === '/billing/plans') return Promise.resolve({ data: plans });
        if (url === '/billing/subscription') {
          return Promise.resolve({
            data: {
              ...subscription,
              tier: 'pro',
              plan: { id: 'pro', name: 'Pro' },
              billing: {
                status: 'past_due',
                can_manage: true,
              },
            },
          });
        }
        return Promise.reject(new Error(`Unhandled GET: ${url}`));
      });

      render(<BillingTab />);

      const note = await screen.findByText(
        /Your last payment for Pro did not go through\. Update your card in Manage billing to keep the plan\./
      );
      expect(note).toHaveClass('gc-text-danger');
    });
  });

  describe('actions and checkout interactions', () => {
    it('opens Stripe billing portal when clicking Manage billing', async () => {
      const user = userEvent.setup();
      const assignMock = vi.fn();
      delete window.location;
      window.location = { ...originalLocation, assign: assignMock };

      try {
        mocks.api.get.mockImplementation((url) => {
          if (url === '/billing/plans') return Promise.resolve({ data: plans });
          if (url === '/billing/subscription') {
            return Promise.resolve({
              data: {
                ...subscription,
                billing: { status: 'active', can_manage: true },
              },
            });
          }
          return Promise.reject(new Error(`Unhandled GET: ${url}`));
        });
        mocks.api.post.mockResolvedValue({ data: { url: 'https://billing.stripe.com/session_test' } });

        render(<BillingTab />);

        await user.click(await screen.findByRole('button', { name: 'Manage billing' }));

        await waitFor(() => {
          expect(mocks.api.post).toHaveBeenCalledWith('/billing/portal');
          expect(assignMock).toHaveBeenCalledWith('https://billing.stripe.com/session_test');
        });
      } finally {
        window.location = originalLocation;
      }
    });

    it('switches to free tier directly via API', async () => {
      const user = userEvent.setup();
      mocks.user = { id: 'u-1', email: 'test@example.com', tier: 'pro' };

      mocks.api.get.mockImplementation((url) => {
        if (url === '/billing/plans') return Promise.resolve({ data: plans });
        if (url === '/billing/subscription') {
          return Promise.resolve({
            data: {
              ...subscription,
              tier: 'pro',
              billing: { status: null, can_manage: false },
            },
          });
        }
        return Promise.reject(new Error(`Unhandled GET: ${url}`));
      });

      mocks.api.post.mockResolvedValue({
        data: {
          ...subscription,
          tier: 'free',
          plan: { id: 'free', name: 'Free' },
        },
      });

      render(<BillingTab />);

      const switchBtn = await screen.findByRole('button', { name: 'Switch to Free' });
      await user.click(switchBtn);

      await waitFor(() => {
        expect(mocks.api.post).toHaveBeenCalledWith('/billing/subscription', { tier: 'free' });
        expect(mocks.setUser).toHaveBeenCalledWith(expect.objectContaining({ tier: 'free' }));
        const freeCard = screen.getByText('Free').closest('.gc-price-card');
        expect(within(freeCard).getByText('Current Plan', { selector: '.gc-current-pill' })).toBeInTheDocument();
        expect(within(freeCard).getByRole('button', { name: 'Current Plan' })).toBeDisabled();
      });
    });

    it('displays error if switching plan fails', async () => {
      const user = userEvent.setup();
      mocks.user = { id: 'u-1', email: 'test@example.com', tier: 'pro' };

      mocks.api.get.mockImplementation((url) => {
        if (url === '/billing/plans') return Promise.resolve({ data: plans });
        if (url === '/billing/subscription') {
          return Promise.resolve({
            data: {
              ...subscription,
              tier: 'pro',
              billing: { status: null, can_manage: false },
            },
          });
        }
        return Promise.reject(new Error(`Unhandled GET: ${url}`));
      });

      mocks.api.post.mockRejectedValue({
        response: { data: { detail: 'Cannot downgrade while exceeding limits.' } },
      });

      render(<BillingTab />);

      const switchBtn = await screen.findByRole('button', { name: 'Switch to Free' });
      await user.click(switchBtn);

      expect(
        await screen.findByText('Cannot downgrade while exceeding limits.')
      ).toBeInTheDocument();
    });

    it('opens and closes checkout modal when clicking upgrade button', async () => {
      const user = userEvent.setup();
      render(<BillingTab />);

      const upgradeBtn = await screen.findByRole('button', { name: 'Upgrade to Pro' });
      await user.click(upgradeBtn);

      expect(screen.getByTestId('checkout-modal')).toBeInTheDocument();
      expect(screen.getByText('Modal for Pro')).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Close Checkout' }));
      expect(screen.queryByTestId('checkout-modal')).not.toBeInTheDocument();
    });

    it('confirms checkout payment upon checkout modal completion', async () => {
      const user = userEvent.setup();
      render(<BillingTab />);

      const upgradeBtn = await screen.findByRole('button', { name: 'Upgrade to Pro' });
      await user.click(upgradeBtn);

      mocks.api.get.mockImplementation((url) => {
        if (url === '/billing/checkout/sess_123') {
          return Promise.resolve({
            data: {
              status: 'complete',
              subscription: {
                ...subscription,
                tier: 'pro',
                plan: { id: 'pro', name: 'Pro' },
                billing: { status: 'active', can_manage: true },
              },
            },
          });
        }
        return Promise.reject(new Error(`Unhandled GET: ${url}`));
      });

      await user.click(screen.getByRole('button', { name: 'Complete Payment' }));

      await waitFor(() => {
        expect(mocks.toast.success).toHaveBeenCalledWith('You are now on Pro.');
        expect(mocks.setUser).toHaveBeenCalledWith(expect.objectContaining({ tier: 'pro' }));
      });
    });

    it('handles checkout redirect URL parameter and confirms subscription', async () => {
      delete window.location;
      window.location = {
        ...originalLocation,
        search: '?checkout=sess_returned_999&tab=billing',
        pathname: '/workspaces',
      };
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState');

      try {
        mocks.api.get.mockImplementation((url) => {
          if (url === '/billing/plans') return Promise.resolve({ data: plans });
          if (url === '/billing/subscription') return Promise.resolve({ data: subscription });
          if (url === '/billing/checkout/sess_returned_999') {
            return Promise.resolve({
              data: {
                status: 'complete',
                subscription: {
                  ...subscription,
                  tier: 'pro',
                  plan: { id: 'pro', name: 'Pro' },
                  billing: { status: 'active', can_manage: true },
                },
              },
            });
          }
          return Promise.reject(new Error(`Unhandled GET: ${url}`));
        });

        render(<BillingTab />);

        expect(replaceStateSpy).toHaveBeenCalledWith(null, '', '/workspaces');
        await waitFor(() => {
          expect(mocks.toast.success).toHaveBeenCalledWith('You are now on Pro.');
        });
      } finally {
        replaceStateSpy.mockRestore();
        window.location = originalLocation;
      }
    });
  });
});
