/* Copyright 2017-present, The Visdom Authors */

import { useId } from 'react';
import { CHARTS } from './start/chartData';
import { digitCells, heatCells } from './start/tileData';

function chartTraces(lines, { x, y, width, height }) {
  const values = lines.flatMap(line => line.y);
  const low = Math.min(...values);
  const high = Math.max(...values);
  return lines.map(({ c, y: samples }) => ({
    color: c,
    points: samples.map((value, index) => {
      const step = x + width * index / (samples.length - 1);
      const level = y + height * (high - value) / (high - low);
      return `${step.toFixed(1)},${level.toFixed(1)}`;
    }).join(' '),
  }));
}

const traces = [
  ...chartTraces(CHARTS.loss2, { x: 0, y: 43, width: 235, height: 115 }),
  ...chartTraces(CHARTS.acc, { x: 515, y: 92, width: 185, height: 74 }),
];
const matrix = heatCells('Confusion matrix', 3);
const samples = digitCells(1);

export default function FooterWordmark() {
  const id = useId();
  const letters = `${id}-letters`;
  const clip = `${id}-clip`;
  const grid = `${id}-grid`;

  return (
    <svg className="site-wordmark" viewBox="0 0 700 205" role="img" aria-label="visdom" focusable="false" pointerEvents="none">
      <defs aria-hidden="true">
        <clipPath id={clip}><use href={`#${letters}`} /></clipPath>
        <pattern id={grid} width="22" height="22" patternUnits="userSpaceOnUse">
          <path d="M0 22V0H22" fill="none" stroke="var(--pub-ice)" strokeWidth="2" />
        </pattern>
      </defs>
      <g aria-hidden="true">
        <text id={letters} x="350" y="180" textAnchor="middle" textLength="686" lengthAdjust="spacingAndGlyphs">visdom</text>
        <g className="site-wordmark-plots" display="none" clipPath={`url(#${clip})`}>
          <rect width="700" height="205" fill="var(--pub-white)" />
          <rect width="700" height="205" fill={`url(#${grid})`} />
          {traces.map(({ color, points }, index) => (
            <polyline key={color} points={points} fill="none" stroke={`color-mix(in srgb, ${color} 70%, var(--pub-white))`}
              strokeWidth="3.5" strokeDasharray={index === 1 ? '7 4' : undefined} />
          ))}
          <g transform="translate(235 31)" fill="color-mix(in srgb, var(--pub-teal) 75%, var(--pub-white))">
            {matrix.map((cell, index) => (
              <rect key={index} x={index % 8 * 17} y={Math.floor(index / 8) * 17} width="16" height="16" fillOpacity={cell.intensity} />
            ))}
          </g>
          <g transform="translate(371 37)">
            {samples.map((cell, index) => (
              <g key={cell.path} transform={`translate(${index % 3 * 48} ${Math.floor(index / 3) * 69})`}>
                <rect x="1" y="1" width="46" height="67" fill="color-mix(in srgb, var(--pub-raspberry) 74%, var(--pub-white))" />
                <svg x="3" y="5" width="42" height="59" viewBox="0 0 26 27">
                  <path d={cell.path} fill="none" stroke="var(--pub-white)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </g>
            ))}
          </g>
        </g>
      </g>
    </svg>
  );
}
