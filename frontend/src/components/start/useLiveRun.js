/* Copyright 2017-present, The Visdom Authors */

import { useEffect, useState } from 'react';
import { LIVE_POINTS, LIVE_START, LIVE_TICK_MS } from './chartData';

export default function useLiveRun(ref, enabled = true) {
  const [count, setCount] = useState(LIVE_START);
  useEffect(() => {
    if (!enabled || !ref.current) return;
    const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    let visible = !window.IntersectionObserver;
    let timer;
    const update = () => {
      clearInterval(timer);
      if (visible && !document.hidden && !motion?.matches) {
        timer = setInterval(() => setCount(n => n >= LIVE_POINTS ? LIVE_START : n + 1), LIVE_TICK_MS);
      }
    };
    const observer = window.IntersectionObserver && new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      update();
    });
    observer?.observe(ref.current);
    motion?.addEventListener('change', update);
    document.addEventListener('visibilitychange', update);
    update();
    return () => {
      clearInterval(timer);
      observer?.disconnect();
      motion?.removeEventListener('change', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, [ref, enabled]);
  return count;
}
