/* Copyright 2017-present, The Visdom Authors */
import { describe, expect, it } from 'vitest';

import { formatJoined, formatLastSignIn, planName } from '../profileDetails';

describe('planName', () => {
  it('names each tier the billing catalog defines', () => {
    expect(planName('free')).toBe('Free');
    expect(planName('pro')).toBe('Pro');
    expect(planName('enterprise')).toBe('Enterprise');
  });

  it('falls back to Free for a missing or unknown tier', () => {
    expect(planName(undefined)).toBe('Free');
    expect(planName('platinum')).toBe('Free');
  });
});

describe('formatJoined', () => {
  it('renders a readable date', () => {
    expect(formatJoined('2026-01-15T10:30:00Z')).toContain('2026');
  });

  it('returns null rather than Invalid Date', () => {
    expect(formatJoined(null)).toBeNull();
    expect(formatJoined(undefined)).toBeNull();
    expect(formatJoined('not a date')).toBeNull();
  });
});

describe('formatLastSignIn', () => {
  it('renders a date and a time', () => {
    const rendered = formatLastSignIn('2026-01-15T10:30:00Z');
    expect(rendered).toContain('2026');
    expect(rendered).toContain(' at ');
  });

  it('explains the empty case rather than showing nothing', () => {
    expect(formatLastSignIn(null)).toBe('This is your first sign-in');
    expect(formatLastSignIn(undefined)).toBe('This is your first sign-in');
  });

  it('returns null rather than Invalid Date', () => {
    expect(formatLastSignIn('not a date')).toBeNull();
  });
});
