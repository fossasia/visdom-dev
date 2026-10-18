/* Copyright 2017-present, The Visdom Authors */
import { describe, expect, it } from 'vitest';

import { expiringHeading, formatDay, isExpiringSoon, retentionSummary } from '../retention';

const notice = (overrides) => ({
  plan: 'Free',
  days: 7,
  state: 'active',
  starts_on: null,
  warn_days: 3,
  expiring: [],
  ...overrides,
});

describe('retentionSummary', () => {
  it('says a plan that keeps everything keeps everything', () => {
    expect(retentionSummary(notice({ plan: 'Enterprise', days: null, state: 'forever' }))).toContain(
      'for as long as the workspace exists'
    );
  });

  it('says nothing is removed yet before deleting is switched on', () => {
    const text = retentionSummary(notice({ state: 'not_enforced' }));
    expect(text).toContain('7 days');
    expect(text).toContain('not being removed yet');
  });

  it('names the day deleting starts', () => {
    const text = retentionSummary(notice({ state: 'scheduled', starts_on: '2026-10-15' }));
    expect(text).toContain('15 October 2026');
    expect(text).toContain('main environment is always kept');
  });

  it('gives nothing for no notice', () => {
    expect(retentionSummary(null)).toBeNull();
  });
});

describe('expiringHeading', () => {
  it('points at the start day when scheduled', () => {
    expect(expiringHeading(notice({ state: 'scheduled', starts_on: '2026-10-15' }))).toContain('15 October 2026');
  });

  it('points at the next few days once active', () => {
    expect(expiringHeading(notice())).toContain('next 3 days');
  });
});

describe('isExpiringSoon', () => {
  it('only warns when something is actually going', () => {
    expect(isExpiringSoon(notice({ expiring: ['old'] }))).toBe(true);
    expect(isExpiringSoon(notice({ expiring: [] }))).toBe(false);
    expect(isExpiringSoon(notice({ expiring: null }))).toBe(false);
    expect(isExpiringSoon(notice({ state: 'not_enforced', expiring: ['old'] }))).toBe(false);
  });
});

describe('formatDay', () => {
  it('reads a plain date without shifting it by the time zone', () => {
    expect(formatDay('2026-10-01')).toBe('1 October 2026');
  });
});
