/* Copyright 2017-present, The Visdom Authors */
import { describe, expect, it } from 'vitest';

import { supportHref } from '../supportContact';

describe('supportHref', () => {
  it('turns an address into a mail link with a subject', () => {
    expect(supportHref('team@example.org')).toBe(
      'mailto:team@example.org?subject=Custom%20Visdom%20plan'
    );
  });

  it('keeps a web link or mail link as it is', () => {
    expect(supportHref('https://example.org/contact')).toBe('https://example.org/contact');
    expect(supportHref('mailto:team@example.org')).toBe('mailto:team@example.org');
  });

  it('offers no link when nothing is configured', () => {
    expect(supportHref('')).toBeNull();
    expect(supportHref(null)).toBeNull();
    expect(supportHref('   ')).toBeNull();
  });

  it('refuses anything that is not a mail or web link', () => {
    expect(supportHref('javascript:alert(1)')).toBeNull();
    expect(supportHref('example.org')).toBeNull();
  });
});
