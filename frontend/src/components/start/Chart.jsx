/* Copyright 2017-present, The Visdom Authors */

import { useId, useState } from 'react';

export default function Chart({ lines, label, range, slots = lines[0].y.length, drawOnEntry = false }) {
  const clipId = useId();
  const [selected, setSelected] = useState(null);
  const values = range || lines.flatMap(line => line.y);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const last = lines[0].y.length - 1;
  const index = Math.min(selected ?? last, last);
  const x = i => 3 + i / Math.max(1, slots - 1) * 94;
  const y = v => 91 - (v - lo) / (hi - lo || 1) * 82;
  const value = lines.map(line => line.y[index].toFixed(3)).join(' / ');
  const inspect = event => {
    const { left, width } = event.currentTarget.getBoundingClientRect();
    const fraction = ((event.clientX - left) / width - 0.03) / 0.94;
    setSelected(Math.max(0, Math.min(last, Math.round(fraction * (slots - 1)))));
  };
  const keyDown = event => {
    const next = { ArrowLeft: index - 1, ArrowDown: index - 1, ArrowRight: index + 1,
      ArrowUp: index + 1, Home: 0, End: last, Enter: index, ' ': index }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    setSelected(Math.min(last, Math.max(0, next)));
  };
  return (
    <div className="st-chart" {...(label ? {
      role: 'slider', tabIndex: 0, 'aria-label': label, 'aria-valuemin': 1,
      'aria-valuemax': last + 1, 'aria-valuenow': index + 1,
      'aria-valuetext': `Point ${index + 1}, ${value}`,
      onPointerMove: inspect, onPointerDown: inspect,
      onPointerLeave: event => { if (event.pointerType === 'mouse') setSelected(null); },
      onFocus: () => setSelected(n => n ?? last), onBlur: () => setSelected(null), onKeyDown: keyDown,
    } : {})}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {drawOnEntry && <defs>
          <clipPath id={clipId}><rect width="100" height="100" /></clipPath>
        </defs>}
        <path className="st-chart-grid" d="M0 25h100 M0 50h100 M0 75h100 M20 0v100 M40 0v100 M60 0v100 M80 0v100"
          fill="none" stroke="var(--pub-rule)" vectorEffect="non-scaling-stroke" />
        {lines.map((line, i) => (
          <polyline key={i} points={line.y.map((v, j) => `${x(j).toFixed(2)},${y(v).toFixed(2)}`).join(' ')}
            fill="none" stroke={line.c} strokeWidth="2" strokeDasharray={i ? '6 3' : undefined}
            clipPath={drawOnEntry ? `url(#${clipId})` : undefined} vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
      {selected !== null && <>
        <span className="st-marker" style={{ left: `${x(index)}%`, top: `${y(lines[0].y[index])}%` }} />
        <span className="st-readout" aria-hidden="true">{index + 1} · {value}</span>
      </>}
    </div>
  );
}
