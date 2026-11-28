/* Copyright 2017-present, The Visdom Authors */

import { useRef, useState } from 'react';
import { copyToClipboard } from '../../utils/clipboard';
import { CLIENT_INSTALL } from '../../utils/quickstart';
import Chart from './Chart';
import { BLUE, LIVE_POINTS, LIVE_TARGET } from './chartData';
import useLiveRun from './useLiveRun';

function LivePlot() {
  const ref = useRef(null);
  const [paused, setPaused] = useState(false);
  const count = useLiveRun(ref, !paused);
  return (
    <div ref={ref} className="st-preview-plot">
      <div className="st-demo-toolbar">
        <span>Loss · step {(count * 500).toLocaleString('en-US')}</span>
        <button type="button" onClick={() => setPaused(!paused)}>{paused ? 'Resume' : 'Pause'}</button>
      </div>
      <Chart label="Inspect sample training loss" lines={[{ y: LIVE_TARGET.slice(0, count), c: BLUE }]}
        slots={LIVE_POINTS} range={LIVE_TARGET} />
    </div>
  );
}

function Roles() {
  const [roles, setRoles] = useState({ ana: 'Admin', raj: 'Member', sam: 'Viewer' });
  return (
    <ul className="st-demo-list">
      {Object.entries(roles).map(([name, role]) => (
        <li key={name}>
          <label htmlFor={`role-${name}`}>{name}@fossasia.org</label>
          <select id={`role-${name}`} aria-label={`Role for ${name}@fossasia.org`} value={role}
            onChange={event => setRoles({ ...roles, [name]: event.target.value })}>
            {['Admin', 'Member', 'Viewer'].map(option => <option key={option}>{option}</option>)}
          </select>
        </li>
      ))}
    </ul>
  );
}

function Keys() {
  const [revoked, setRevoked] = useState({});
  return (
    <ul className="st-demo-list">
      {[['lab-gpu-01', 'resnet-sweeps'], ['ci-runner', 'All workspaces']].map(([key, scope]) => (
        <li key={key}>
          <div><strong>{key}</strong><small>{revoked[key] ? 'Revoked' : scope}</small></div>
          <button type="button" onClick={() => setRevoked({ ...revoked, [key]: !revoked[key] })}>
            {revoked[key] ? 'Undo' : 'Revoke'}
          </button>
        </li>
      ))}
    </ul>
  );
}

function JoinRequest({ name }) {
  const [status, setStatus] = useState('');
  const primary = useRef(null);
  return (
    <li>
      <div><strong>{name}@fossasia.org</strong><small>{status || 'Requests to join resnet-sweeps'}</small></div>
      <div className="st-demo-actions">
        <button type="button" ref={primary} onClick={() => setStatus(status ? '' : 'Approved')}>{status ? 'Undo' : 'Approve'}</button>
        {!status && <button type="button" onClick={() => { primary.current.focus(); setStatus('Declined'); }}>Decline</button>}
      </div>
    </li>
  );
}

const Requests = () => (
  <ul className="st-demo-list st-requests">
    {['priya', 'tom', 'mei'].map(name => <JoinRequest key={name} name={name} />)}
  </ul>
);

const TRIALS = [
  [15, 0.001, 128, 0.871], [17, 0.0003, 256, 0.902],
  [16, 0.0001, 256, 0.884], [18, 0.0003, 512, null],
];

function Sweeps() {
  const [order, setOrder] = useState({ column: 0, direction: 1 });
  const { column, direction } = order;
  const sorted = [...TRIALS].sort((a, b) => {
    if (a[column] === null || b[column] === null) return Number(a[column] === null) - Number(b[column] === null);
    return direction * (a[column] - b[column]);
  });
  return (
    <table className="st-trials" aria-label="Example sweep trials">
      <thead><tr>
        {['Trial', 'Rate', 'Batch', 'Accuracy'].map((name, i) => (
          <th key={name} scope="col" aria-sort={i === column ? (direction === 1 ? 'ascending' : 'descending') : undefined}>
            <button type="button" onClick={() => setOrder({ column: i, direction: i === column ? -direction : 1 })}>
              {name}<span aria-hidden="true">{i === column ? (direction === 1 ? ' ↑' : ' ↓') : ' ↕'}</span>
            </button>
          </th>
        ))}
      </tr></thead>
      <tbody>{sorted.map(([trial, rate, batch, accuracy]) => (
        <tr key={trial}><td>{trial}</td><td>{rate.toExponential()}</td><td>{batch}</td><td>{accuracy ?? 'Running'}</td></tr>
      ))}</tbody>
    </table>
  );
}

const EXAMPLE = [
  'vis.line(Y=[loss], X=[step],',
  '         win="loss", update="append")',
  'vis.images(batch, win="samples")',
  'vis.text(notes, win="notes")',
].join('\n');

function Client() {
  const [result, setResult] = useState('');
  const copy = async () => setResult(await copyToClipboard(EXAMPLE) ? 'Copied' : 'Select the Python code to copy it.');
  return (
    <div className="st-client">
      <pre className="st-code" tabIndex="0" aria-label="Install the client"><code>{CLIENT_INSTALL}</code></pre>
      <div className="st-demo-toolbar">
        <span>Python</span><span role="status">{result}</span><button type="button" onClick={copy}>Copy</button>
      </div>
      <pre className="st-code" tabIndex="0" aria-label="Python plotting example"><code>{EXAMPLE}</code></pre>
    </div>
  );
}

const FEATURES = [
  ['Live plots, images and text', 'Line charts, scatter plots, heatmaps, images, audio and video, updated while the run is going.', LivePlot],
  ['Workspaces and roles', 'One workspace per project. Admins manage it, members write to it, viewers only look.', Roles],
  ['Scoped API keys', 'Give each machine or pipeline its own key, set when it expires, and revoke it when you are done.', Keys],
  ['Join links', 'Share one link to bring people in. Each person who opens it asks to join, and an admin approves them.', Requests],
  ['Experiments and sweeps', 'Compare runs in the HParams dashboard, and log Optuna, PyTorch, Keras and XGBoost training as it happens.', Sweeps],
  ['The client you already use', 'Keep your plotting code. Give the Visdom client a key and a workspace, and every call lands here.', Client],
];

export default function FeatureDemos() {
  return (
    <section className="st-features" aria-labelledby="st-get">
      <div className="st-inner">
        <header data-reveal>
          <h2 id="st-get">What you get</h2>
          <p className="st-demo-note">Try the demos. Changes reset when you reload.</p>
        </header>
        {FEATURES.slice(0, 2).map(([name, description, Demo], i) => (
          <section key={name} className="st-feature-row" aria-labelledby={`feature-${i}`}>
            <div data-reveal className="st-feature-copy">
              <h3 id={`feature-${i}`}>{name}</h3>
              <p>{description}</p>
            </div>
            <div data-reveal className="st-frag"><Demo /></div>
          </section>
        ))}
        <ul className="st-feature-list">
          {FEATURES.slice(2).map(([name, description, Demo]) => (
            <li data-reveal key={name}>
              <details open>
                <summary>{name}</summary>
                <div className="st-feature-body">
                  <p>{description}</p>
                  <div className="st-frag"><Demo /></div>
                </div>
              </details>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
