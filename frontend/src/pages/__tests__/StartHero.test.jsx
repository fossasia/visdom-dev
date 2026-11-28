/* Copyright 2017-present, The Visdom Authors */

import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import Start from '../Start';

const renderStart = () => render(<MemoryRouter><Start /></MemoryRouter>);
const board = () => screen.getByRole('region', { name: 'Experiment previews' });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it('fills the available grid as the screen changes size', () => {
  renderStart();
  for (const [width, columns, span] of [[360, 2, 2], [550, 3, 3], [844, 4, 2], [1024, 5, 3], [1280, 6, 2], [1700, 7, 3], [2000, 8, 4], [2560, 10, 4]]) {
    vi.stubGlobal('innerWidth', width);
    fireEvent(window, new Event('resize'));
    expect(board().querySelectorAll('.st-pane')).toHaveLength(columns * 3 - span);
    expect(within(board()).getByRole('heading', { level: 1 })).toBeVisible();
  }
  vi.stubGlobal('innerWidth', 844);
  vi.stubGlobal('innerHeight', 390);
  fireEvent(window, new Event('resize'));
  expect(board().querySelectorAll('.st-pane')).toHaveLength(6);
});

it.each([[375, 320, 'compact', 2], [1280, 240, 'shallow', 2]])(
  'uses complete pane rows on a %i by %i screen', (width, height, mode, panes) => {
    vi.stubGlobal('innerWidth', width);
    vi.stubGlobal('innerHeight', height);
    renderStart();
    expect(board()).toHaveClass(`st-sheet-${mode}`);
    expect(board().querySelectorAll('.st-pane')).toHaveLength(panes);
    expect(within(board()).getByRole('slider', { name: 'Training loss' })).toBeVisible();
  }
);

it('reads a chart point with a pointer or keyboard', () => {
  renderStart();
  const chart = within(board()).getAllByRole('slider')[0];
  vi.spyOn(chart, 'getBoundingClientRect').mockReturnValue({ left: 0, width: 200 });
  fireEvent.pointerDown(chart, { clientX: 0, pointerType: 'touch' });
  expect(chart).toHaveAttribute('aria-valuenow', '1');
  fireEvent.keyDown(chart, { key: 'ArrowRight' });
  expect(chart).toHaveAttribute('aria-valuenow', '2');
  expect(chart).toHaveAttribute('aria-valuetext', expect.stringMatching(/Point 2/));
});

it('ticks only while the board is visible and motion is enabled', () => {
  vi.useFakeTimers();
  let shown;
  vi.stubGlobal('IntersectionObserver', class {
    constructor(callback) { this.callback = callback; }
    observe(element) {
      if (element.getAttribute('aria-label') === 'Experiment previews') {
        shown = (isIntersecting) => this.callback([{ target: element, isIntersecting }]);
      }
    }
    disconnect() {}
    unobserve() {}
  });
  const motion = new EventTarget();
  motion.matches = false;
  vi.stubGlobal('matchMedia', () => motion);
  renderStart();
  const step = () => within(board()).getByText(/step [\d,]+/i).textContent.match(/[\d,]+$/)[0];
  const tick = () => act(() => vi.advanceTimersByTime(700));
  const first = step();
  tick();
  expect(step()).toBe(first);
  act(() => shown(true));
  tick();
  expect(step()).not.toBe(first);
  const second = step();
  act(() => shown(false));
  tick();
  expect(step()).toBe(second);
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  act(() => shown(true));
  fireEvent(document, new Event('visibilitychange'));
  tick();
  expect(step()).toBe(second);
  hidden.mockReturnValue(false);
  motion.matches = true;
  fireEvent(document, new Event('visibilitychange'));
  tick();
  expect(step()).toBe(second);
  motion.matches = false;
  fireEvent(motion, new Event('change'));
  tick();
  expect(step()).not.toBe(second);
  fireEvent.click(within(board()).getByRole('button', { name: 'Pause training loss' }));
  const paused = step();
  tick();
  expect(step()).toBe(paused);
  fireEvent.click(within(board()).getByRole('button', { name: 'Resume training loss' }));
  act(() => shown(false));
  tick();
  expect(step()).toBe(paused);
  act(() => shown(true));
  tick();
  expect(step()).not.toBe(paused);
});

it('makes every heatmap and sample batch a single keyboard stop with pane-specific labels', () => {
  vi.stubGlobal('innerWidth', 2560);
  renderStart();
  for (const [title, readout] of [
    ['Confusion matrix', /true 0 · predicted 0/],
    ['Class predictions', /class 0 · predicted 0/],
    ['Attention weights', /query token 0 · key token 0/],
    ['Class attention', /query token 0 · key token 0/],
    ...['Sample batch', 'Validation batch', 'Augmented batch', 'Training batch · ViT',
      'Validation batch · ViT', 'Validation samples'].map(title => [title, /label \d · pred \d/]),
  ]) {
    const grid = within(board()).getByRole('slider', { name: title });
    expect(grid.tabIndex).toBe(0);
    expect(grid.querySelectorAll('[tabindex]')).toHaveLength(0);
    fireEvent.focus(grid);
    expect(grid).toHaveAttribute('aria-valuetext', expect.stringMatching(readout));
  }
});

it('reads the colour of the hovered heat cell and moves through rows and columns', () => {
  renderStart();
  const grid = within(board()).getByRole('slider', { name: 'Confusion matrix' });
  const cells = grid.querySelectorAll('i');
  fireEvent.pointerMove(cells[21], { pointerType: 'mouse' });
  const alpha = Number(cells[21].style.getPropertyValue('--st-intensity'));
  const readout = `true 2 · predicted 5 · ${alpha.toFixed(2)}`;
  expect(within(grid).getByText(readout)).toBeVisible();
  expect(cells[21]).toHaveClass('st-selected-tile');
  expect(grid).toHaveAttribute('aria-valuetext', readout);
  for (const [key, point] of [['ArrowUp', 14], ['ArrowLeft', 13], ['ArrowDown', 21],
    ['ArrowRight', 22], ['Home', 1], ['ArrowLeft', 1], ['End', 64], ['ArrowRight', 64]]) {
    fireEvent.keyDown(grid, { key });
    expect(grid).toHaveAttribute('aria-valuenow', String(point));
  }
  fireEvent.pointerLeave(grid, { pointerType: 'mouse' });
  expect(grid.querySelector('.st-readout')).toBeNull();
  fireEvent.pointerDown(cells[12], { pointerType: 'touch' });
  fireEvent.pointerLeave(grid, { pointerType: 'touch' });
  expect(grid.querySelector('.st-readout')).toBeVisible();
  fireEvent.blur(grid);
  expect(grid.querySelector('.st-readout')).toBeNull();
});

it('inspects the drawn digit on tap, keeps the touch selection and clears it on blur', () => {
  renderStart();
  const grid = within(board()).getByRole('slider', { name: 'Sample batch' });
  const tiles = grid.querySelectorAll('svg');
  const path = tiles[2].querySelector('path');
  expect(path).toHaveAttribute('d', 'M5 6h15L9 22');
  fireEvent.pointerDown(path, { pointerType: 'touch' });
  const readout = within(grid).getByText(/^label 7 · pred 7 · 0\.\d{2}$/).textContent;
  fireEvent.pointerLeave(grid, { pointerType: 'touch' });
  fireEvent.mouseMove(tiles[0]);
  fireEvent.pointerLeave(grid, { pointerType: 'mouse' });
  expect(within(grid).getByText(readout)).toBeVisible();
  fireEvent.pointerMove(tiles[0], { pointerType: 'mouse' });
  expect(grid).toHaveAttribute('aria-valuetext', expect.stringMatching(/^label 1/));
  fireEvent.pointerLeave(grid, { pointerType: 'mouse' });
  expect(grid.querySelector('.st-readout')).toBeNull();
  fireEvent.pointerDown(tiles[3], { pointerType: 'touch' });
  expect(grid).toHaveAttribute('aria-valuetext', expect.stringMatching(/^label 0/));
  fireEvent.keyDown(grid, { key: 'ArrowRight' });
  expect(grid).toHaveAttribute('aria-valuenow', '5');
  fireEvent.keyDown(grid, { key: 'ArrowUp' });
  expect(grid).toHaveAttribute('aria-valuenow', '2');
  fireEvent.keyDown(grid, { key: 'End' });
  expect(grid).toHaveAttribute('aria-valuenow', '6');
  expect(tiles[5]).toHaveClass('st-selected-tile');
  expect(grid).toHaveAttribute('aria-valuetext', 'label 6 · pred 7 · 0.69');
  fireEvent.blur(grid);
  fireEvent.mouseOver(path);
  expect(grid.querySelector('.st-readout')).toBeNull();
  fireEvent.pointerMove(path, { pointerType: 'mouse' });
  expect(within(grid).getByText(readout)).toBeVisible();
  fireEvent.pointerLeave(grid, { pointerType: 'mouse' });
  expect(grid.querySelector('.st-readout')).toBeNull();
});

it('groups plot strips and traces by measurement and gives attention its own heat scale', () => {
  vi.stubGlobal('innerWidth', 2560);
  renderStart();
  const pane = title => within(board()).getByRole('slider', { name: title }).closest('.st-pane');
  const colour = title => pane(title).style.getPropertyValue('--st-plot-colour');
  for (const [title, family] of [
    ['Training loss', 'blue'], ['Validation loss', 'blue'], ['Validation accuracy', 'green'],
    ['Learning rate', 'cyan'], ['GPU memory, GB', 'muted'], ['Gradient norm', 'muted'],
  ]) {
    expect(colour(title)).toBe(`var(--pub-${family})`);
    expect(pane(title).querySelector('polyline')).toHaveAttribute('stroke', colour(title));
    expect(pane(title).querySelector('path.st-chart-grid')).toBeInTheDocument();
  }
  expect(pane('Validation loss').querySelectorAll('polyline')[1]).toHaveAttribute('stroke-dasharray');
  for (const title of ['Sample batch', 'Validation batch', 'Augmented batch']) {
    expect(colour(title)).toBe('var(--pub-raspberry)');
  }
  expect(colour('Class predictions')).toBe('var(--pub-teal)');
  expect(colour('Confusion matrix')).toBe(colour('Class predictions'));
  expect(colour('Attention weights')).toBe('var(--pub-raspberry)');
  expect(colour('Class attention')).toBe(colour('Attention weights'));
});
