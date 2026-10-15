/* Copyright 2017-present, The Visdom Authors */

import { describe, expect, it } from 'vitest';

import { apiErrorText, tokenFromHash } from '../authLinks';

describe('tokenFromHash', () => {
  it('reads the token from the link fragment', () => {
    expect(tokenFromHash('#token=Ab-_09xyz')).toBe('Ab-_09xyz');
  });

  it('is empty when the link has no token', () => {
    expect(tokenFromHash('')).toBe('');
    expect(tokenFromHash('#other=1')).toBe('');
    expect(tokenFromHash(undefined)).toBe('');
  });
});

describe('apiErrorText', () => {
  it('uses the message the server gave', () => {
    expect(apiErrorText({ response: { data: { detail: 'Link expired.' } } }, 'fallback')).toBe('Link expired.');
  });

  it('joins validation messages', () => {
    const err = { response: { data: { detail: [{ msg: 'too short' }, { msg: 'bad email' }] } } };
    expect(apiErrorText(err, 'fallback')).toBe('too short, bad email');
  });

  it('falls back when the server said nothing useful', () => {
    expect(apiErrorText(new Error('Network Error'), 'fallback')).toBe('fallback');
    expect(apiErrorText({ response: { data: { detail: [] } } }, 'fallback')).toBe('fallback');
  });
});
