/* Copyright 2017-present, The Visdom Authors */
import { useCallback, useEffect, useState } from 'react';
import { CheckCircle, CreditCard, LifeBuoy, Rocket, Sparkles, Zap } from 'lucide-react';
import { api, useAuth } from '../../context/AuthContext';
import { cachedGet, invalidate } from '../../utils/requestCache';
import { parseApiError } from '../../utils/helpers';
import { supportHref } from '../../utils/supportContact';
import { formatBytes } from '../../utils/usageFormat';
import { planAction, subscriptionNote } from '../../utils/billing';
import { useToast } from '../toast/useToast';
import CheckoutModal from './CheckoutModal';

const CONFIRM_TRIES = 8;
const CONFIRM_DELAY_MS = 1500;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const PLAN_ICONS = { free: Zap, pro: Sparkles, enterprise: Rocket };

const formatLimit = (limit) =>
  limit === null || limit === undefined ? 'Unlimited' : limit.toLocaleString();

const BillingTab = () => {
  const { user, setUser } = useAuth();
  const [plans, setPlans] = useState([]);
  const [subscription, setSubscription] = useState(null);
  const [loading, setLoading] = useState(true);
  const [switchingTo, setSwitchingTo] = useState(null);
  const [error, setError] = useState('');
  const [buying, setBuying] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [openingPortal, setOpeningPortal] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [plansData, subData] = await Promise.all([
        cachedGet('/billing/plans', () => api.get('/billing/plans').then((res) => res.data)),
        cachedGet('/billing/subscription', () => api.get('/billing/subscription').then((res) => res.data)),
      ]);
      setPlans(plansData);
      setSubscription(subData);
    } catch (err) {
      setError(parseApiError(err, 'Failed to load billing information.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const currentTier = subscription?.tier || user?.tier || 'free';
  const contactHref = supportHref(subscription?.support_contact);
  const billing = subscription?.billing;
  const note = subscriptionNote(billing, subscription?.plan?.name);

  const settle = useCallback(
    (data) => {
      invalidate('/billing/subscription');
      setSubscription(data);
      if (user && data.tier !== user.tier) setUser({ ...user, tier: data.tier });
    },
    [user, setUser]
  );

  const confirmCheckout = useCallback(
    async (sessionId) => {
      setBuying(null);
      setConfirming(true);
      setError('');
      try {
        for (let attempt = 0; attempt < CONFIRM_TRIES; attempt += 1) {
          const { data } = await api.get(`/billing/checkout/${encodeURIComponent(sessionId)}`);
          if (data.subscription.billing?.status) {
            settle(data.subscription);
            toast.success(`You are now on ${data.subscription.plan.name}.`);
            return;
          }
          if (data.status === 'expired') break;
          await wait(CONFIRM_DELAY_MS);
        }
        setError('The payment has not been confirmed yet. Reload this page in a minute to see your plan.');
      } catch (err) {
        setError(parseApiError(err, 'The payment could not be confirmed. Reload this page in a minute.'));
      } finally {
        setConfirming(false);
      }
    },
    [settle, toast]
  );

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const returned = params.get('checkout');
    if (!returned) return;
    params.delete('checkout');
    params.delete('tab');
    const rest = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${rest ? `?${rest}` : ''}`);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    confirmCheckout(returned);
  }, [confirmCheckout]);

  const openPortal = async () => {
    setOpeningPortal(true);
    setError('');
    try {
      const { data } = await api.post('/billing/portal');
      window.location.assign(data.url);
    } catch (err) {
      setError(parseApiError(err, 'Billing could not be opened. Try again shortly.'));
      setOpeningPortal(false);
    }
  };

  const handleSwitch = async (tier) => {
    setSwitchingTo(tier);
    setError('');
    try {
      const response = await api.post('/billing/subscription', { tier });
      settle(response.data);
    } catch (err) {
      setError(parseApiError(err, 'Failed to change plan.'));
    } finally {
      setSwitchingTo(null);
    }
  };

  if (loading) {
    return (
      <section className="gc-panel">
        <div className="gc-empty">Loading billing information...</div>
      </section>
    );
  }

  const renderAction = (plan) => {
    const action = planAction(plan, { currentTier, billing });
    const busy = switchingTo !== null || confirming || openingPortal;
    switch (action.kind) {
      case 'current':
      case 'unavailable':
        return (
          <button className="gc-btn gc-w-full gc-mt-1" type="button" disabled>
            {action.label}
          </button>
        );
      case 'contact':
        return contactHref ? (
          <a
            className="gc-btn gc-w-full gc-mt-1"
            href={contactHref}
            target={contactHref.startsWith('mailto:') ? undefined : '_blank'}
            rel="noreferrer"
          >
            {action.label}
          </a>
        ) : (
          <button className="gc-btn gc-w-full gc-mt-1" type="button" disabled>
            {action.label}
          </button>
        );
      case 'portal':
        return (
          <button className="gc-btn gc-w-full gc-mt-1" type="button" onClick={openPortal} disabled={busy}>
            {action.label}
          </button>
        );
      case 'checkout':
        return (
          <button
            className="gc-btn gc-btn-primary gc-w-full gc-mt-1"
            type="button"
            onClick={() => setBuying(plan)}
            disabled={busy}
          >
            {action.label}
          </button>
        );
      default:
        return (
          <button
            className="gc-btn gc-btn-primary gc-w-full gc-mt-1"
            type="button"
            onClick={() => handleSwitch(plan.id)}
            disabled={busy}
          >
            {switchingTo === plan.id ? 'Switching...' : action.label}
          </button>
        );
    }
  };

  const usage = subscription?.usage;
  const usageItems = usage
    ? [
        { label: 'Workspaces', ...usage.workspaces },
        { label: 'Team seats', ...usage.members },
        { label: 'API keys', ...usage.api_keys },
        ...(usage.storage ? [{ label: 'Storage', ...usage.storage, format: formatBytes }] : []),
      ]
    : [];

  return (
    <div className="gc-flex-col-gap-lg">
      <section className="gc-panel">
        <div className="gc-panel-header">
          <span className="gc-panel-title">
            <CreditCard size={15} />
            Subscription Plans
          </span>
        </div>

        {error && <div className="gc-form-error">{error}</div>}

        <div className="gc-pricing-grid">
          {plans.map((plan) => {
            const Icon = PLAN_ICONS[plan.id] || Zap;
            const isCurrent = plan.id === currentTier;
            const isEnterprise = plan.price === null;
            return (
              <div key={plan.id} className={`gc-price-card ${isCurrent ? 'current' : ''}`}>
                {isCurrent && <span className="gc-current-pill">Current Plan</span>}
                <div className="gc-price-card-header">
                  <Icon size={16} />
                  {plan.name}
                </div>
                <div className="gc-price-amount">
                  {isEnterprise ? 'Custom' : `$${plan.price}`}
                  {!isEnterprise && <span> / month</span>}
                </div>
                <ul className="gc-price-features">
                  {plan.features.map((feature) => (
                    <li key={feature}>
                      <CheckCircle size={13} className="gc-shrink-0 gc-text-success" />
                      {feature}
                    </li>
                  ))}
                </ul>

                {renderAction(plan)}
              </div>
            );
          })}
        </div>

        {confirming && <div className="gc-text-desc-muted gc-mt-sm">Confirming your payment...</div>}
        {note && (
          <div className={`gc-text-desc-muted gc-mt-sm ${note.tone === 'danger' ? 'gc-text-danger' : ''}`}>{note.text}</div>
        )}
        {billing?.can_manage && (
          <button className="gc-btn gc-mt-sm" type="button" onClick={openPortal} disabled={openingPortal}>
            {openingPortal ? 'Opening...' : 'Manage billing'}
          </button>
        )}
      </section>

      {buying && <CheckoutModal plan={buying} onClose={() => setBuying(null)} onComplete={confirmCheckout} />}

      <section className="gc-panel">
        <div className="gc-panel-header">
          <span className="gc-panel-title">
            <LifeBuoy size={16} /> Need a custom plan?
          </span>
        </div>
        <div className="gc-text-desc-muted">
          If none of these fit, for example you need more workspaces or members than a plan
          allows, the Visdom team can set up a plan for you.
        </div>
        {contactHref && (
          <a
            className="gc-btn gc-btn-primary gc-mt-sm"
            href={contactHref}
            target={contactHref.startsWith('mailto:') ? undefined : '_blank'}
            rel="noreferrer"
          >
            Contact us
          </a>
        )}
      </section>

      <section className="gc-panel">
        <div className="gc-panel-header">
          <span className="gc-panel-title">Usage This Cycle</span>
        </div>

        {usageItems.map((item) => {
          const unlimited = item.limit === null || item.limit === undefined;
          const pct = unlimited
            ? 0
            : Math.min(100, Math.round((item.used / Math.max(item.limit, 1)) * 100));
          const over = !unlimited && item.used > item.limit;
          return (
            <div key={item.label} className="gc-meter">
              <div className="gc-meter-label">
                <span>{item.label}</span>
                <span className={over ? 'gc-text-danger' : ''}>
                  {item.format ? item.format(item.used) : item.used.toLocaleString()} /{' '}
                  {unlimited ? 'Unlimited' : item.format ? item.format(item.limit) : formatLimit(item.limit)}
                </span>
              </div>
              {!unlimited && (
                <div className="gc-meter-track">
                  <div className="gc-meter-fill" style={{ width: `${pct}%` }} />
                </div>
              )}
            </div>
          );
        })}
      </section>
    </div>
  );
};

export default BillingTab;
