/* Copyright 2017-present, The Visdom Authors */
import { describe, expect, it } from 'vitest';

import { cachedGet, clearRequestCache } from '../requestCache';

describe('cachedGet', () => {
  it('does not keep an answer that arrives after the cache was cleared', async () => {
    let finish;
    const first = cachedGet('/usage', () => new Promise((resolve) => { finish = resolve; }));
    clearRequestCache();
    finish({ owner: 'previous' });
    await first;

    const fresh = await cachedGet('/usage', () => Promise.resolve({ owner: 'current' }));

    expect(fresh).toEqual({ owner: 'current' });
  });
});
