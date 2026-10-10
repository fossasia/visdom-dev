/* Copyright 2017-present, The Visdom Authors */
import { describe, expect, it } from 'vitest';

import {
  pickActiveWorkspace,
  requestedWorkspaceSlug,
} from '../activeWorkspace';

const alpha = { id: 'a', slug: 'alpha', name: 'Alpha' };
const beta = { id: 'b', slug: 'beta', name: 'Beta' };
const list = [alpha, beta];

describe('requestedWorkspaceSlug', () => {
  it('reads the slug the visualizations link carries back', () => {
    expect(requestedWorkspaceSlug('?workspace=beta')).toBe('beta');
  });

  it('returns null when the console was opened directly', () => {
    expect(requestedWorkspaceSlug('')).toBeNull();
    expect(requestedWorkspaceSlug(undefined)).toBeNull();
    expect(requestedWorkspaceSlug('?tab=members')).toBeNull();
  });

  it('decodes a slug that needed escaping', () => {
    expect(requestedWorkspaceSlug('?workspace=my%20space')).toBe('my space');
  });
});

describe('pickActiveWorkspace', () => {
  it('opens the workspace the link names rather than the first one', () => {
    expect(pickActiveWorkspace(null, list, 'beta')).toBe(beta);
  });

  it('falls back to the first workspace with no slug', () => {
    expect(pickActiveWorkspace(null, list, null)).toBe(alpha);
  });

  it('falls back to the first workspace when the slug matches nothing', () => {
    expect(pickActiveWorkspace(null, list, 'gone')).toBe(alpha);
  });

  it('keeps the workspace already open, ignoring the slug', () => {
    expect(pickActiveWorkspace(beta, list, 'alpha')).toBe(beta);
  });

  it('drops a workspace that has disappeared since it was selected', () => {
    expect(pickActiveWorkspace({ id: 'gone' }, list, null)).toBeNull();
  });

  it('returns null when there are no workspaces at all', () => {
    expect(pickActiveWorkspace(null, [], 'beta')).toBeNull();
    expect(pickActiveWorkspace(null, undefined, null)).toBeNull();
  });
});
