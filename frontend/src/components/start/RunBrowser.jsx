/* Copyright 2017-present, The Visdom Authors */

import { useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import Chart from './Chart';
import { BLUE, curve, LIVE_POINTS, LIVE_TARGET } from './chartData';
import useLiveRun from './useLiveRun';

const RUNS = [
  { name: 'vit-small-patch16', epoch: '90/90', loss: '0.284', owner: 'Sam', status: 'Done' },
  { name: 'resnet50-aug-mixup', epoch: '63/90', loss: '0.361', owner: 'Raj', status: 'Running' },
  { name: 'resnet50-lr-3e-4', epoch: '12/90', loss: '1.902', owner: 'Ana', status: 'Stopped' },
  { name: 'resnet50-base', owner: 'Ana', status: 'Running', live: true },
  { name: 'efficientnet-b0', epoch: '90/90', loss: '0.297', owner: 'Raj', status: 'Done' },
  { name: 'optuna-trial-17', epoch: '20/20', loss: '0.455', owner: 'Sam', status: 'Done' },
  { name: 'optuna-trial-18', epoch: '7/20', loss: '0.731', owner: 'Sam', status: 'Running' },
  { name: 'convnext-tiny', epoch: '34/90', loss: '0.508', owner: 'Ana', status: 'Running' },
  { name: 'resnet18-baseline', epoch: '90/90', loss: '0.402', owner: 'Raj', status: 'Done' },
].map((run, i) => {
  if (run.live) return run;
  const loss = Number(run.loss);
  const series = curve(parseInt(run.epoch, 10), 2.8, loss, 0.13, i + 1);
  series[series.length - 1] = loss;
  return { ...run, series };
});

const RunDetails = ({ run }) => {
  const ref = useRef(null);
  const count = useLiveRun(ref, run.live === true);
  const series = run.live ? LIVE_TARGET.slice(0, count) : run.series;
  const epoch = run.live ? `${Math.round(count / LIVE_POINTS * 90)}/90` : run.epoch;
  const loss = series.at(-1).toFixed(3);
  return (
    <section ref={ref} className="st-run-detail" id="st-run-detail" aria-labelledby="st-run-name">
      <h3 id="st-run-name">{run.name}</h3>
      <dl className="st-run-metrics">
        {Object.entries({ Epoch: epoch, Loss: loss, Owner: run.owner, Status: run.status }).map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className={label === 'Status' ? `st-status st-status-${value.toLowerCase()}` : undefined}>{value}</dd>
          </div>
        ))}
      </dl>
      <div className="st-preview-plot">
        <div className="st-plot-title">Training loss</div>
        <Chart label={`Training loss for ${run.name}`} lines={[{ y: series, c: BLUE }]}
          slots={run.live ? LIVE_POINTS : undefined} range={run.live ? LIVE_TARGET : undefined} />
      </div>
    </section>
  );
};

const isWide = () => window.innerWidth >= 1024;
const subscribe = notify => {
  window.addEventListener('resize', notify);
  return () => window.removeEventListener('resize', notify);
};

export default function RunBrowser() {
  const [selected, setSelected] = useState(3);
  const buttons = useRef([]);
  const previousTop = useRef(null);
  const wide = useSyncExternalStore(subscribe, isWide);
  const choose = index => {
    if (index === selected) return;
    if (!wide) previousTop.current = buttons.current[index].getBoundingClientRect().top;
    setSelected(index);
  };
  useLayoutEffect(() => {
    if (previousTop.current === null) return;
    const shift = buttons.current[selected].getBoundingClientRect().top - previousTop.current;
    if (shift) window.scrollBy(0, shift);
    previousTop.current = null;
  }, [selected]);
  const keyDown = (event, i) => {
    const next = { ArrowDown: i + 1, ArrowUp: i - 1, ArrowRight: i + 1, ArrowLeft: i - 1,
      Home: 0, End: RUNS.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const index = (next + RUNS.length) % RUNS.length;
    buttons.current[index].focus();
    choose(index);
  };
  const detail = <RunDetails key={selected} run={RUNS[selected]} />;
  return (
    <section className="st-board" aria-labelledby="st-runs">
      <div className="st-inner">
        <h2 data-reveal id="st-runs">Every run, as it happens</h2>
        <div data-reveal className="st-run-browser">
          <ul className="st-runs" aria-label="Example runs">
            {RUNS.map((run, i) => (
              <li key={run.name}>
                <button type="button" ref={el => { buttons.current[i] = el; }}
                  aria-expanded={selected === i} aria-controls={selected === i ? 'st-run-detail' : undefined}
                  onClick={() => choose(i)} onKeyDown={event => keyDown(event, i)}>
                  <span>{run.name}</span>
                  <span className={`st-status st-status-${run.status.toLowerCase()}`}>{run.status}</span>
                </button>
                {!wide && selected === i && detail}
              </li>
            ))}
          </ul>
          {wide && detail}
        </div>
      </div>
    </section>
  );
}
