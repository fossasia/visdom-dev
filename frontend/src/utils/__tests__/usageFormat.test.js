/* Copyright 2017-present, The Visdom Authors */
import { describe, expect, it } from 'vitest';

import { formatActiveTime, formatBytes, monthLabel } from '../usageFormat';

describe('formatActiveTime', () => {
  it('shows minutes alone under an hour', () => {
    expect(formatActiveTime(0)).toBe('0m');
    expect(formatActiveTime(45)).toBe('45m');
  });

  it('shows hours and minutes, dropping zero minutes', () => {
    expect(formatActiveTime(200)).toBe('3h 20m');
    expect(formatActiveTime(120)).toBe('2h');
  });

  it('treats a missing value as none', () => {
    expect(formatActiveTime(undefined)).toBe('0m');
    expect(formatActiveTime(-5)).toBe('0m');
  });
});

describe('formatBytes', () => {
  it('uses the largest unit that keeps the number readable', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(88 * 1024 * 1024)).toBe('88.0 MB');
    expect(formatBytes(3 * 1024 ** 3)).toBe('3.0 GB');
  });

  it('drops the decimal once the number is large', () => {
    expect(formatBytes(250 * 1024 * 1024)).toBe('250 MB');
  });
});

describe('monthLabel', () => {
  it('names the month the period started in', () => {
    expect(monthLabel('2026-09-01T00:00:00+00:00')).toContain('2026');
  });

  it('falls back when the date is unreadable', () => {
    expect(monthLabel('nonsense')).toBe('This month');
  });
});
