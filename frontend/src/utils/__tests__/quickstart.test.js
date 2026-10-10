/* Copyright 2017-present, The Visdom Authors */

import { describe, expect, it } from 'vitest';

import { KEY_PLACEHOLDER, plotSnippet, serverArgs } from '../quickstart';

const at = (href) => new URL(href);

describe('serverArgs', () => {
  it('uses 443 on https, where the browser hides the port', () => {
    expect(serverArgs(at('https://visdom.dev/'))).toEqual({ server: 'https://visdom.dev', port: '443' });
  });

  it('keeps an explicit port, as a dev server has', () => {
    expect(serverArgs(at('http://localhost:5173/'))).toEqual({ server: 'http://localhost', port: '5173' });
  });
});

describe('plotSnippet', () => {
  it('fills in the key and the workspace so it can be pasted as is', () => {
    const code = plotSnippet({ apiKey: 'visdom_live_abc', workspace: 'team-alpha', location: at('https://visdom.dev/') });
    expect(code).toContain('api_key="visdom_live_abc"');
    expect(code).toContain('workspace="team-alpha"');
    expect(code).toContain('server="https://visdom.dev", port=443, base_url="/vis"');
    expect(code).not.toContain(KEY_PLACEHOLDER);
  });

  it('falls back to placeholders when there is no key to show', () => {
    const code = plotSnippet({ workspace: 'team-alpha', location: at('https://visdom.dev/') });
    expect(code).toContain(`api_key="${KEY_PLACEHOLDER}"`);
  });
});
