/* Copyright 2017-present, The Visdom Authors */
export const BLUE = 'var(--pub-blue)';
const MUTED = 'var(--pub-muted)';
const CYAN = 'var(--pub-cyan)';
const GREEN = 'var(--pub-green)';

export const LIVE_POINTS = 120;
export const LIVE_START = 50;
export const LIVE_TICK_MS = 700;

export const curve = (n, start, end, noise, seed) => {
  let s = seed;
  const rnd = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
  return Array.from({ length: n }, (_, i) => end + (start - end) * Math.exp((-4 * i) / (n - 1)) + (rnd() - 0.5) * noise);
};

const warmupCosine = Array.from({ length: 60 }, (_, i) => (i < 8 ? i / 8 : Math.cos(((i - 8) / 52) * (Math.PI / 2))));

export const CHARTS = {
  acc: [{ y: curve(60, 0.2, 0.9, 0.04, 3), c: GREEN }],
  acc2: [{ y: curve(60, 0.1, 0.95, 0.03, 8), c: GREEN }],
  acc3: [{ y: curve(60, 0.15, 0.9, 0.03, 17), c: GREEN }],
  lr: [{ y: warmupCosine, c: CYAN }],
  loss2: [{ y: curve(80, 2.3, 0.35, 0.12, 5), c: BLUE }, { y: curve(80, 2.3, 0.45, 0.06, 9), c: 'var(--pub-blue-deep)' }],
  loss3: [{ y: curve(70, 2.1, 0.3, 0.1, 11), c: BLUE }],
  loss4: [{ y: curve(40, 2.2, 0.4, 0.1, 13), c: BLUE }],
  gpu: [{ y: curve(60, 4, 11.2, 0.4, 2).map((v) => 15 - v), c: MUTED }],
  grad: [{ y: curve(60, 5, 1, 0.8, 4), c: MUTED }],
};

export const LIVE_TARGET = curve(LIVE_POINTS, 2.3, 0.4, 0.1, 31);
