/* Copyright 2017-present, The Visdom Authors */

import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import Start from '../Start';
import { readFileSync } from 'node:fs';
import { copyToClipboard } from '../../utils/clipboard';

vi.mock('../../utils/clipboard', () => ({ copyToClipboard: vi.fn() }));
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const sectionStyles = readFileSync('src/css/start-sections.css', 'utf8');
const visit = () => render(<MemoryRouter><Start /></MemoryRouter>);
const panel = name => within(screen.getByRole('region', { name }));
const featureDemo = name => within(screen.getByText(name, { selector: 'summary' }).closest('details'));

it('keeps all nine runs reachable and displays the selected run metrics and chart', () => {
  visit();
  const runs = panel('Every run, as it happens');
  const buttons = runs.getAllByRole('button');
  expect(buttons).toHaveLength(9);
  fireEvent.click(buttons[8]);
  const detail = panel('resnet18-baseline');
  expect(detail.getByText('90/90')).toBeVisible();
  expect(detail.getByText('0.402')).toBeVisible();
  expect(detail.getByText('Raj')).toBeVisible();
  expect(detail.getByText('Done')).toBeVisible();
  expect(detail.getByText('Done')).toHaveClass('st-status-done');
  expect(detail.getByRole('slider')).toBeVisible();
  fireEvent.keyDown(buttons[8], { key: 'ArrowUp' });
  expect(buttons[7]).toHaveFocus();
  expect(buttons[7]).toHaveAttribute('aria-expanded', 'true');
  expect(runs.getAllByRole('button')).toHaveLength(9);
});

it('places the active chart beneath its row on small screens and alongside the list on desktop', () => {
  vi.stubGlobal('innerWidth', 390);
  visit();
  const runs = panel('Every run, as it happens');
  const last = runs.getAllByRole('button')[8];
  fireEvent.click(last);
  const detail = () => runs.getByRole('region', { name: 'resnet18-baseline' });
  expect(last.nextElementSibling).toBe(detail());
  vi.stubGlobal('innerWidth', 1024);
  fireEvent(window, new Event('resize'));
  expect(runs.getByRole('list').nextElementSibling).toBe(detail());
});

it('updates the live run and lets a visitor pause the separate plot demo', () => {
  vi.useFakeTimers();
  visit();
  const live = panel('resnet50-base').getByRole('slider');
  const demo = panel('Live plots, images and text');
  const chart = demo.getByRole('slider');
  const first = live.getAttribute('aria-valuemax');
  const sample = chart.getAttribute('aria-valuemax');
  fireEvent.click(demo.getByRole('button', { name: 'Pause' }));
  act(() => vi.advanceTimersByTime(700));
  expect(live).not.toHaveAttribute('aria-valuemax', first);
  expect(chart).toHaveAttribute('aria-valuemax', sample);
  fireEvent.click(demo.getByRole('button', { name: 'Resume' }));
  act(() => vi.advanceTimersByTime(700));
  expect(chart).not.toHaveAttribute('aria-valuemax', sample);
});

it('changes a role and supports undo for keys and join requests', () => {
  visit();
  const role = screen.getByRole('combobox', { name: 'Role for raj@fossasia.org' });
  fireEvent.change(role, { target: { value: 'Viewer' } });
  expect(role).toHaveValue('Viewer');
  const key = within(featureDemo('Scoped API keys').getByText('lab-gpu-01').closest('li'));
  fireEvent.click(key.getByRole('button', { name: 'Revoke' }));
  expect(key.getByText('Revoked')).toBeVisible();
  fireEvent.click(key.getByRole('button', { name: 'Undo' }));
  expect(key.getByRole('button', { name: 'Revoke' })).toBeVisible();
  const request = within(featureDemo('Join links').getByText('priya@fossasia.org').closest('li'));
  for (const [action, result] of [['Approve', 'Approved'], ['Decline', 'Declined']]) {
    fireEvent.click(request.getByRole('button', { name: action }));
    expect(request.getByText(result)).toBeVisible();
    fireEvent.click(request.getByRole('button', { name: 'Undo' }));
  }
});

it('sorts numeric trials in both directions and copies the displayed Python', async () => {
  visit();
  const sweeps = featureDemo('Experiments and sweeps');
  const sort = sweeps.getByRole('button', { name: 'Accuracy' });
  fireEvent.click(sort);
  expect(sweeps.getAllByRole('row')[1]).toHaveTextContent('0.871');
  fireEvent.click(sort);
  expect(sweeps.getAllByRole('row')[1]).toHaveTextContent('0.902');
  expect(sort.closest('th')).toHaveAttribute('aria-sort', 'descending');
  const client = featureDemo('The client you already use');
  copyToClipboard.mockResolvedValue(true);
  fireEvent.click(client.getByRole('button', { name: 'Copy' }));
  expect(copyToClipboard).toHaveBeenCalledWith(client.getByText(/vis.images\(batch/).textContent);
  expect(await client.findByText('Copied')).toBeVisible();
});

it('plots the four loss values from the example script beside the sign-up link', () => {
  visit();
  const cta = panel('Your first plot in five minutes');
  const chart = cta.getByRole('slider', { name: 'Training loss from the example script' });
  const script = screen.getByLabelText('Connect your script to Visdom').textContent;
  const values = JSON.parse(script.match(/enumerate\((\[[^\]]+\])\)/)[1]);
  expect(values).toHaveLength(4);
  expect(chart).toHaveAttribute('aria-valuemax', String(values.length));
  fireEvent.keyDown(chart, { key: 'Home' });
  values.forEach((loss, i) => {
    expect(chart).toHaveAttribute('aria-valuetext', `Point ${i + 1}, ${loss.toFixed(3)}`);
    fireEvent.keyDown(chart, { key: 'ArrowRight' });
  });
  expect(cta.getByRole('link', { name: 'Create an account' })).toHaveAttribute('href', '/register');
});

it('wraps long example lines while preserving Python indentation for copying', () => {
  visit();
  render(<style>{sectionStyles}</style>);
  for (const name of ['Connect your script to Visdom', 'Install the client', 'Python plotting example']) {
    const code = screen.getByLabelText(name);
    expect(getComputedStyle(code).whiteSpace).toBe('pre-wrap');
    expect(getComputedStyle(code).overflowWrap).toBe('anywhere');
  }
  expect(screen.getByLabelText('Connect your script to Visdom').textContent).toContain('\n    vis.line(');
  expect(screen.getByLabelText('Python plotting example').textContent).toContain('\n         win=');
});

it('opens all four feature demos by default and lets visitors collapse them independently', () => {
  visit();
  const features = screen.getByRole('region', { name: 'What you get' });
  expect(within(features).getAllByRole('region')).toHaveLength(2);
  expect(features.querySelectorAll('details[open]')).toHaveLength(4);
  const summary = within(features).getByText('Scoped API keys', { selector: 'summary' });
  const key = within(features).getByText('lab-gpu-01');
  expect(key).toBeVisible();
  fireEvent.click(summary);
  expect(key).not.toBeVisible();
  expect(features.querySelectorAll('details[open]')).toHaveLength(3);
  fireEvent.click(summary);
  expect(key).toBeVisible();
});

it('keeps the four steps compact and the full working script just below them', () => {
  visit();
  const steps = screen.getByRole('region', { name: 'From sign-up to first plot' });
  const list = within(steps).getByRole('list');
  expect(within(list).getAllByRole('listitem')).toHaveLength(4);
  expect(list).not.toContainElement(screen.getByLabelText('Connect your script to Visdom'));
  const example = within(steps).getByText('Show the complete Python example', { selector: 'summary' });
  fireEvent.click(example);
  expect(example.closest('details')).toHaveAttribute('open');
  expect(example.closest('details')).toContainElement(screen.getByLabelText('Connect your script to Visdom'));
});

it('copies the self-hosted install command and explains how to copy it manually on failure', async () => {
  visit();
  const section = panel('Built in the open');
  const copy = section.getByRole('button', { name: 'Copy install command' });
  const command = section.getByText('pip install visdom');
  copyToClipboard.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  fireEvent.click(copy);
  expect(await section.findByText('Select the command to copy it.')).toBeVisible();
  fireEvent.click(copy);
  expect(await section.findByText('Copied')).toBeVisible();
  expect(copyToClipboard).toHaveBeenLastCalledWith(command.textContent);
});

it('reveals the closing chart once, after it enters a visible tab', () => {
  let trigger;
  const targets = new Set();
  vi.stubGlobal('IntersectionObserver', class {
    constructor(notify) { this.notify = notify; }
    observe(element) {
      if (element.matches('.st-first-plot')) {
        trigger = () => this.notify([{ target: element, isIntersecting: true }]);
        targets.add(element);
      }
    }
    unobserve(element) { targets.delete(element); }
    disconnect() { targets.clear(); }
  });
  visit();
  const figure = screen.getByText('Step 3').closest('figure');
  expect(targets.has(figure)).toBe(true);
  const clip = figure.querySelector('clipPath');
  expect(clip?.querySelector('rect')).toBeInTheDocument();
  expect(figure.querySelector('polyline')).toHaveAttribute('clip-path', `url(#${clip.id})`);
  expect(figure.querySelector('.st-chart-grid')).not.toHaveAttribute('clip-path');
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  try {
    fireEvent(document, new Event('visibilitychange'));
    act(() => trigger());
    expect(figure).not.toHaveClass('st-entered');
    hidden.mockReturnValue(false);
    fireEvent(document, new Event('visibilitychange'));
    act(() => trigger());
    expect(figure).toHaveClass('st-entered');
    expect(targets.has(figure)).toBe(false);
    figure.classList.remove('st-entered');
    act(() => trigger());
    expect(figure).not.toHaveClass('st-entered');
  } finally {
    hidden.mockRestore();
  }
});

it('leaves the finished chart visible with reduced motion or without an observer', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal('IntersectionObserver', undefined);
  visit();
  const figure = screen.getByText('Step 3').closest('figure');
  expect(figure).toBeVisible();
  expect(figure).not.toHaveClass('st-entered');
  expect(figure.querySelector('polyline')).toBeInTheDocument();
});
