/* Copyright 2017-present, The Visdom Authors */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copyToClipboard, downloadTextFile } from '../clipboard';

const setContext = ({ secure, writeText }) => {
  Object.defineProperty(window, 'isSecureContext', {
    value: secure,
    configurable: true,
  });
  Object.defineProperty(navigator, 'clipboard', {
    value: writeText ? { writeText } : undefined,
    configurable: true,
  });
};

describe('copyToClipboard', () => {
  beforeEach(() => {
    document.execCommand = vi.fn(() => true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('refuses empty text without reaching for the clipboard', async () => {
    const writeText = vi.fn();
    setContext({ secure: true, writeText });

    expect(await copyToClipboard('')).toBe(false);
    expect(writeText).not.toHaveBeenCalled();
    expect(document.execCommand).not.toHaveBeenCalled();
  });

  it('uses the clipboard API when the page is secure', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setContext({ secure: true, writeText });

    expect(await copyToClipboard('visdom_live_abc')).toBe(true);
    expect(writeText).toHaveBeenCalledWith('visdom_live_abc');
    expect(document.execCommand).not.toHaveBeenCalled();
  });

  it('falls back to the textarea when the page is not secure', async () => {
    const writeText = vi.fn();
    setContext({ secure: false, writeText });

    expect(await copyToClipboard('visdom_live_abc')).toBe(true);
    expect(writeText).not.toHaveBeenCalled();
    expect(document.execCommand).toHaveBeenCalledWith('copy');
  });

  it('falls back when the browser exposes no clipboard API', async () => {
    setContext({ secure: true, writeText: null });

    expect(await copyToClipboard('visdom_live_abc')).toBe(true);
    expect(document.execCommand).toHaveBeenCalledWith('copy');
  });

  it('falls back when the clipboard API rejects', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'));
    setContext({ secure: true, writeText });

    expect(await copyToClipboard('visdom_live_abc')).toBe(true);
    expect(document.execCommand).toHaveBeenCalledWith('copy');
  });

  it('reports failure when the fallback cannot copy either', async () => {
    setContext({ secure: false, writeText: null });
    document.execCommand = vi.fn(() => false);

    expect(await copyToClipboard('visdom_live_abc')).toBe(false);
  });

  it('leaves no textarea behind', async () => {
    setContext({ secure: false, writeText: null });
    await copyToClipboard('visdom_live_abc');

    expect(document.querySelectorAll('textarea')).toHaveLength(0);
  });
});

describe('downloadTextFile', () => {
  it('reports failure rather than throwing when the blob cannot be made', () => {
    const original = URL.createObjectURL;
    URL.createObjectURL = vi.fn(() => {
      throw new Error('nope');
    });

    expect(downloadTextFile('key.txt', 'secret')).toBe(false);

    URL.createObjectURL = original;
  });
});
