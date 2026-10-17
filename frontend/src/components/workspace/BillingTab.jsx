/* Copyright 2017-present, The Visdom Authors */
import { useCallback, useEffect, useState } from 'react';
import { CheckCircle, CreditCard, Rocket, Sparkles, Zap } from 'lucide-react';
import { api, useAuth } from '../../context/AuthContext';
import { cachedGet, invalidate } from '../../utils/requestCache';
import { parseApiError } from '../../utils/helpers';

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

  const handleSwitch = async (tier) => {
    setSwitchingTo(tier);
    setError('');
    try {
      const response = await api.post('/billing/subscription', { tier });
      invalidate('/billing/subscription');
      setSubscription(response.data);
      if (user) setUser({ ...user, tier: response.data.tier });
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

  const usage = subscription?.usage;
  const usageItems = usage
    ? [
        { label: 'Workspaces', ...usage.workspaces },
        { label: 'Team seats', ...usage.members },
        { label: 'API keys', ...usage.api_keys },
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

                {isCurrent ? (
                  <button className="gc-btn gc-w-full gc-mt-1" type="button" disabled>
                    Current Plan
                  </button>
                ) : isEnterprise ? (
                  <a
                    className="gc-btn gc-w-full gc-mt-1"
                    href="mailto:sales@visdom.cloud?subject=Enterprise%20plan"
                  >
                    Contact Sales
                  </a>
                ) : plan.id !== 'free' ? (
                  <button
                    className="gc-btn gc-w-full gc-mt-1"
                    type="button"
                    disabled
                  >
                    Paid upgrade unavailable
                  </button>
                ) : (
                  <button
                    className="gc-btn gc-btn-primary gc-w-full gc-mt-1"
                    type="button"
                    onClick={() => handleSwitch(plan.id)}
                    disabled={switchingTo !== null}
                  >
                    {switchingTo === plan.id ? 'Switching...' : `Switch to ${plan.name}`}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        <div className="gc-text-desc-muted gc-mt-sm">
          Paid plan access requires a verified subscription. Contact sales for Enterprise access.
        </div>
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
                  {item.used.toLocaleString()} / {formatLimit(item.limit)}
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
