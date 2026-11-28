/* Copyright 2017-present, The Visdom Authors */

import { memo, useMemo, useRef, useState } from 'react';
import { digitCells, heatCells } from './tileData';

const TilePane = memo(function TilePane({ type, title, seed }) {
  const samples = type === 'digits';
  const columns = samples ? 3 : 8;
  const cells = useMemo(() => samples ? digitCells(seed) : heatCells(title, seed), [samples, title, seed]);
  const [selected, setSelected] = useState(null);
  const touchSelection = useRef(false);
  const index = selected ?? 0;
  const last = cells.length - 1;

  const inspect = event => {
    const tile = event.target.closest('[data-tile]');
    if (tile) {
      setSelected(Number(tile.dataset.tile));
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const rows = cells.length / columns;
    const col = Math.max(0, Math.min(columns - 1, Math.floor((event.clientX - rect.left) / rect.width * columns)));
    const row = Math.max(0, Math.min(rows - 1, Math.floor((event.clientY - rect.top) / rect.height * rows)));
    setSelected(row * columns + col);
  };

  const keyDown = event => {
    const col = index % columns;
    const next = {
      ArrowLeft: col > 0 ? index - 1 : index, ArrowRight: col < columns - 1 ? index + 1 : index,
      ArrowUp: index >= columns ? index - columns : index, ArrowDown: index + columns <= last ? index + columns : index,
      Home: 0, End: last, Enter: index, ' ': index,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    touchSelection.current = false;
    setSelected(next);
  };

  return (
    <div className={samples ? 'st-samples' : 'st-heat'} role="slider" tabIndex={0} aria-label={title}
      aria-valuemin={1} aria-valuemax={cells.length} aria-valuenow={index + 1} aria-valuetext={cells[index].readout}
      onPointerDown={event => {
        event.currentTarget.focus({ preventScroll: true });
        touchSelection.current = event.pointerType === 'touch';
        inspect(event);
      }}
      onPointerMove={event => {
        if (event.pointerType === 'touch' || event.nativeEvent.sourceCapabilities?.firesTouchEvents) return;
        touchSelection.current = false;
        inspect(event);
      }}
      onPointerLeave={event => { if (event.pointerType !== 'touch' && !touchSelection.current) setSelected(null); }}
      onFocus={() => setSelected(current => current ?? 0)}
      onBlur={() => { touchSelection.current = false; setSelected(null); }} onKeyDown={keyDown}>
      {cells.map((cell, i) => {
        const props = { 'data-tile': i, 'aria-hidden': true, className: selected === i ? 'st-selected-tile' : undefined };
        return samples ? (
          <svg key={i} {...props} viewBox="0 0 26 27">
            <path d={cell.path} fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round"
              strokeLinejoin="round" transform={`rotate(${(seed + i) % 5 * 4 - 8} 13 13)`} />
          </svg>
        ) : <i key={i} {...props} style={{ '--st-intensity': cell.intensity }} />;
      })}
      {selected !== null && <span className="st-readout" aria-hidden="true"
        style={index >= cells.length / 2 ? { top: 4, bottom: 'auto' } : undefined}>{cells[selected].readout}</span>}
    </div>
  );
});

export default TilePane;
