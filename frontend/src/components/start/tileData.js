/* Copyright 2017-present, The Visdom Authors */

const DIGITS = [
  'M12 5C4 6 3 22 11 22S22 5 15 5Z', 'M7 10l7-5-2 17',
  'M5 10Q10 0 17 7Q21 12 6 21l14-1', 'M6 6Q21 1 16 11l-5 1q15-3 6 8-5 5-12-1',
  'M15 4L5 15h15m-4-9-2 17', 'M19 5H9l-3 9q11-7 12 1 0 10-13 5',
  'M17 4Q5 8 6 18c1 8 13 4 12-2q-2-7-12-1', 'M5 6h15L9 22',
  'M12 12C-1 7 18-2 18 7s-16 9-11 14 20-1 5-9Z', 'M17 12C5 18 3 7 12 5s9 5 0 17',
];

export const heatCells = (title, seed) => Array.from({ length: 64 }, (_, i) => {
  const row = Math.floor(i / 8);
  const col = i % 8;
  const value = (0.08 + (row === col ? 0.9 : Math.abs(Math.sin(i * 7.3 + seed)) * 0.48)).toFixed(2);
  let axes = `query token ${row} · key token ${col}`;
  if (title === 'Confusion matrix') axes = `true ${row} · predicted ${col}`;
  if (title === 'Class predictions') axes = `class ${row} · predicted ${col}`;
  return { intensity: value, readout: `${axes} · ${value}` };
});

export const digitCells = seed => Array.from({ length: 6 }, (_, i) => {
  const digit = (seed + i * 3) % DIGITS.length;
  const wrong = (seed + i) % 6 === 0;
  const prediction = wrong ? (digit + 1) % DIGITS.length : digit;
  const score = (wrong ? 0.64 + i / 100 : 0.91 + (seed + i) % 9 / 100).toFixed(2);
  return { path: DIGITS[digit], readout: `label ${digit} · pred ${prediction} · ${score}` };
});
