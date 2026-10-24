/* Copyright 2017-present, The Visdom Authors */
import { describe, expect, it } from 'vitest';

import { planAction, subscriptionNote } from '../billing';

const free = { id: 'free', name: 'Free', price: 0, checkout: false };
const pro = { id: 'pro', name: 'Pro', price: 29, checkout: true };
const custom = { id: 'enterprise', name: 'Enterprise', price: null, checkout: false };
const paying = { enabled: true, status: 'active', renews_at: '2030-01-01T00:00:00Z', ends_at: null };

describe('planAction', () => {
  it('marks the plan the account is on', () => {
    expect(planAction(pro, { currentTier: 'pro', billing: paying }).kind).toBe('current');
  });

  it('sends a free account to checkout for a paid plan', () => {
    expect(planAction(pro, { currentTier: 'free', billing: { enabled: true } })).toEqual({
      kind: 'checkout',
      label: 'Upgrade to Pro',
    });
  });

  it('does not offer a paid plan that cannot be bought', () => {
    expect(planAction({ ...pro, checkout: false }, { currentTier: 'free', billing: { enabled: false } }).kind).toBe(
      'unavailable'
    );
  });

  it('sends a paying account to the portal to change or cancel', () => {
    expect(planAction(free, { currentTier: 'pro', billing: paying }).kind).toBe('portal');
    expect(planAction({ ...pro, id: 'team' }, { currentTier: 'pro', billing: paying }).kind).toBe('portal');
  });

  it('lets an account without a subscription switch to a free plan', () => {
    expect(planAction(free, { currentTier: 'pro', billing: { enabled: true } }).kind).toBe('switch');
  });

  it('asks to get in touch for a custom plan', () => {
    expect(planAction(custom, { currentTier: 'free', billing: { enabled: true } }).kind).toBe('contact');
  });
});

describe('subscriptionNote', () => {
  it('says nothing without a subscription', () => {
    expect(subscriptionNote({ enabled: true }, 'Free')).toBeNull();
  });

  it('names the renewal day', () => {
    expect(subscriptionNote(paying, 'Pro').text).toBe('Your Pro plan renews on 1 January 2030.');
  });

  it('names the last day of a plan that will not renew', () => {
    const note = subscriptionNote({ ...paying, renews_at: null, ends_at: '2030-01-01T00:00:00Z' }, 'Pro');
    expect(note.text).toBe('Your Pro plan ends on 1 January 2030 and will not renew.');
  });

  it('warns when a payment failed', () => {
    const note = subscriptionNote({ ...paying, status: 'past_due' }, 'Pro');
    expect(note.tone).toBe('danger');
    expect(note.text).toContain('did not go through');
  });
});
