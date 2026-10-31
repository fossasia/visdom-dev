/* Copyright 2017-present, The Visdom Authors */
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import usePageTitle, { formatPageTitle } from '../usePageTitle';

describe('usePageTitle', () => {
  beforeEach(() => {
    document.title = 'Visdom';
  });

  it('prefixes the page name to the app name', () => {
    renderHook(() => usePageTitle('Sign in'));
    expect(document.title).toBe('Sign in · Visdom');
  });

  it('falls back to the app name when there is no page name', () => {
    expect(formatPageTitle('')).toBe('Visdom');
    expect(formatPageTitle(undefined)).toBe('Visdom');
  });

  it('follows a title that changes while mounted', () => {
    const { rerender } = renderHook(({ title }) => usePageTitle(title), {
      initialProps: { title: 'Dashboard' },
    });
    rerender({ title: 'Lab A' });
    expect(document.title).toBe('Lab A · Visdom');
  });

  it('restores the previous title on unmount', () => {
    const { unmount } = renderHook(() => usePageTitle('Reset password'));
    unmount();
    expect(document.title).toBe('Visdom');
  });
});
