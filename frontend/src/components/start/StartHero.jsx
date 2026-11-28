/* Copyright 2017-present, The Visdom Authors */

import { useRef, useState, useSyncExternalStore } from 'react';
import { Link } from 'react-router-dom';
import Chart from './Chart';
import TilePane from './TilePane';
import useLiveRun from './useLiveRun';
import '../../css/start-hero.css';
import { BLUE, CHARTS, LIVE_POINTS, LIVE_TARGET } from './chartData';

const PANES = [
  ['Training loss', 'live'], ['Sample batch', 'digits'], ['Validation accuracy', 'acc'],
  ['Confusion matrix', 'heat'], ['Learning rate', 'lr'], ['Validation loss', 'loss2'],
  ['Gradient norm', 'grad'], ['Validation batch', 'digits'], ['GPU memory, GB', 'gpu'],
  ['Top-5 accuracy', 'acc2'], ['Attention weights', 'attention'], ['Training loss · ViT', 'loss3'],
  ['Augmented batch', 'digits'], ['Validation accuracy · ViT', 'acc3'], ['Learning rate · ViT', 'lr'],
  ['Class predictions', 'heat'], ['Validation loss · ViT', 'loss4'], ['Training batch · ViT', 'digits'],
  ['Accuracy · ConvNeXt', 'acc2'], ['Gradient norm · ViT', 'grad'], ['Validation batch · ViT', 'digits'],
  ['Class attention', 'attention'], ['Loss · ConvNeXt', 'loss2'], ['Learning rate · ConvNeXt', 'lr'],
  ['Validation samples', 'digits'], ['Accuracy · ResNet', 'acc'],
];

const tileColours = { digits: 'var(--pub-raspberry)', heat: 'var(--pub-teal)', attention: 'var(--pub-raspberry)' };
const columnBreakpoints = [[2560, 10], [1920, 8], [1680, 7], [1280, 6], [1024, 5], [768, 4], [480, 3], [0, 2]];
const screenColumns = () => columnBreakpoints.find(([minWidth]) => window.innerWidth >= minWidth)[1];
const screenMode = () => {
  if (window.innerWidth < 480 && window.innerHeight >= 275 && window.innerHeight <= 460) return 'compact';
  if (window.innerHeight <= 345) return 'shallow';
  return window.innerHeight <= 620 ? 'short' : 'regular';
};
const onResize = notify => {
  window.addEventListener('resize', notify);
  return () => window.removeEventListener('resize', notify);
};

export default function StartHero() {
  const boardRef = useRef(null);
  const [paused, setPaused] = useState(false);
  const count = useLiveRun(boardRef, !paused);
  const columns = useSyncExternalStore(onResize, screenColumns);
  const mode = useSyncExternalStore(onResize, screenMode);
  const compact = mode === 'compact';
  const shallow = mode === 'shallow';
  const rowCount = shallow ? 1 : compact ? 2 : 3;
  const span = columns >= 8 || (shallow && columns === 6) ? 4
    : columns === 3 && mode !== 'regular' ? 2 : 2 + columns % 2;
  const pitchRows = mode === 'short' && columns > 2 ? 3 : 1;
  const pitchStart = pitchRows === 3 || compact || shallow ? 1 : 2;
  const live = [{ y: LIVE_TARGET.slice(0, count), c: BLUE }];
  return (
    <section className={`st-sheet st-sheet-${mode}`} ref={boardRef} aria-label="Experiment previews" style={{
      gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
    }}>
      <div className="st-pitch" style={{
        gridColumn: `${1 + Math.floor((columns - span) / 2)} / span ${span}`,
        gridRow: `${pitchStart} / span ${pitchRows}`,
      }}>
        <h1>Watch training live, together.</h1>
        <p>{compact || shallow ? 'Live plots, images and text for your team.' :
          'Your plots, images and text in the browser while training runs. Hosted for your team, no server to set up.'}</p>
        <div className="st-pitch-actions">
          <Link to="/register" className="st-btn">Get started</Link>
          <Link to="/login">Sign in</Link>
        </div>
      </div>
      {PANES.slice(0, columns * rowCount - pitchRows * span).map(([title, type], i) => {
        const lines = type === 'live' ? live : CHARTS[type];
        const colour = tileColours[type] || lines[0].c;
        return (
          <div key={title} className="st-pane" style={{ '--st-plot-colour': colour }}>
            <div className="st-pane-strip">
              {title}
              {type === 'live' && <button type="button" className="st-live-toggle" aria-label={paused ? 'Resume training loss' : 'Pause training loss'}
                onClick={() => setPaused(!paused)}>{paused ? 'Resume' : 'Pause'}</button>}
            </div>
            <div className="st-pane-body">
              {tileColours[type] ? <TilePane type={type} title={title} seed={i} /> : (
                <Chart label={title} lines={lines}
                  slots={type === 'live' ? LIVE_POINTS : undefined} range={type === 'live' ? LIVE_TARGET : undefined} />
              )}
              {type === 'live' && <span className="st-live">{paused ? 'Paused' : 'Live'} · step {(count * 500).toLocaleString('en-US')}</span>}
            </div>
          </div>
        );
      })}
    </section>
  );
}
