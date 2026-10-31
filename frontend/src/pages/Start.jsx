/* Copyright 2017-present, The Visdom Authors */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CLIENT_INSTALL, plotSnippet } from '../utils/quickstart';

const GITHUB_VISDOM = 'https://github.com/fossasia/visdom';
const GITHUB_VISDOM_DEV = 'https://github.com/fossasia/visdom-dev';

const BLUE = '#1a6fb0';
const NAVY = '#3b5998';
const ORANGE = '#f9a557';
const GREEN = '#1e7e34';

const LIVE_POINTS = 120;
const LIVE_START = 50;
const LIVE_TICK_MS = 700;

const curve = (n, start, end, noise, seed) => {
  let s = seed;
  const rnd = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
  return Array.from({ length: n }, (_, i) => end + (start - end) * Math.exp((-4 * i) / (n - 1)) + (rnd() - 0.5) * noise);
};

const flip = (values) => values.map((v) => 1.05 - v);

const warmupCosine = Array.from({ length: 60 }, (_, i) => (i < 8 ? i / 8 : Math.cos(((i - 8) / 52) * (Math.PI / 2))));

const CHARTS = {
  acc: [{ y: flip(curve(60, 0.2, 0.9, 0.04, 3)), c: GREEN }],
  acc2: [{ y: flip(curve(60, 0.1, 0.95, 0.03, 8)), c: GREEN }],
  acc3: [{ y: flip(curve(60, 0.15, 0.9, 0.03, 17)), c: GREEN }],
  lr: [{ y: warmupCosine, c: ORANGE }],
  loss2: [{ y: curve(80, 2.3, 0.35, 0.12, 5), c: BLUE }, { y: curve(80, 2.3, 0.45, 0.06, 9), c: ORANGE }],
  loss3: [{ y: curve(70, 2.1, 0.3, 0.1, 11), c: BLUE }],
  loss4: [{ y: curve(40, 2.2, 0.4, 0.1, 13), c: BLUE }],
  gpu: [{ y: curve(60, 4, 11.2, 0.4, 2).map((v) => 15 - v), c: NAVY }],
  grad: [{ y: curve(60, 5, 1, 0.8, 4), c: NAVY }],
};

const LIVE_TARGET = curve(LIVE_POINTS, 2.3, 0.4, 0.1, 31);

const W = 300;
const H = 200;

const points = (values, lo, hi, slots) =>
  values
    .map((v, i) => `${((i / Math.max(slots - 1, 1)) * W).toFixed(1)},${(H - 14 - ((v - lo) / (hi - lo || 1)) * (H - 28)).toFixed(1)}`)
    .join(' ');

const Chart = ({ lines, range, slots }) => {
  const all = range || lines.flatMap((l) => l.y);
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      {lines.map((l, i) => (
        <polyline
          key={i}
          points={points(l.y, lo, hi, slots || l.y.length)}
          fill="none"
          stroke={l.c}
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </svg>
  );
};

const Heat = ({ seed }) => (
  <div className="st-heat" aria-hidden="true">
    {Array.from({ length: 64 }, (_, i) => {
      const r = i % 9 === 0 ? 0.9 : Math.abs(Math.sin(i * 7.3 + seed)) * 0.35;
      return <i key={i} style={{ background: `rgba(33, 133, 208, ${r.toFixed(2)})` }} />;
    })}
  </div>
);

const Pane = ({ title, tone, height, children }) => (
  <div className="st-pane" style={height ? { height } : undefined}>
    <div className={`st-pane-strip st-tone-${tone}`}>{title}</div>
    <div className="st-pane-body">{children}</div>
  </div>
);

const Samples = ({ ids }) => (
  <div className="st-imgs">
    {ids.map((id, i) => (
      <img key={`${id}-${i}`} src={`/start/samples/${id}.jpg`} alt="Sample image from a training batch" width="400" height="400" />
    ))}
  </div>
);

const prefersReducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

const useLiveRun = () => {
  const [count, setCount] = useState(LIVE_START);
  useEffect(() => {
    if (prefersReducedMotion()) {
      return undefined;
    }
    const timer = setInterval(() => {
      setCount((n) => (n >= LIVE_POINTS ? LIVE_START : n + 1));
    }, LIVE_TICK_MS);
    return () => clearInterval(timer);
  }, []);
  return count;
};

const useReveal = (ref) => {
  useEffect(() => {
    const root = ref.current;
    if (!root) {
      return undefined;
    }
    const items = Array.from(root.querySelectorAll('.st-rise, .st-shutter'));
    if (!('IntersectionObserver' in window)) {
      items.forEach((el) => el.classList.add('st-in'));
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('st-in');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 }
    );
    items.forEach((el, i) => {
      el.style.transitionDelay = `${(i % 3) * 70}ms`;
      observer.observe(el);
    });
    return () => observer.disconnect();
  }, [ref]);
};

const RUNS = [
  { name: 'vit-small-patch16', epoch: '90/90', loss: '0.284', owner: 'Sam', status: 'Done' },
  { name: 'resnet50-aug-mixup', epoch: '63/90', loss: '0.361', owner: 'Raj', status: 'Running' },
  { name: 'resnet50-lr-3e-4', epoch: '12/90', loss: '1.902', owner: 'Ana', status: 'Stopped' },
  {
    name: 'resnet50-base',
    owner: 'Ana',
    status: 'Running',
    live: true,
    detail: 'Started 2 hours ago from lab-gpu-01. Four windows: loss, val accuracy, learning rate and a sample batch, updated every 500 steps.',
  },
  { name: 'efficientnet-b0', epoch: '90/90', loss: '0.297', owner: 'Raj', status: 'Done' },
  { name: 'optuna-trial-17', epoch: '20/20', loss: '0.455', owner: 'Sam', status: 'Done' },
  { name: 'optuna-trial-18', epoch: '7/20', loss: '0.731', owner: 'Sam', status: 'Running' },
  { name: 'convnext-tiny', epoch: '34/90', loss: '0.508', owner: 'Ana', status: 'Running' },
  { name: 'resnet18-baseline', epoch: '90/90', loss: '0.402', owner: 'Raj', status: 'Done' },
];

const STATUS_CLASS = { Running: 'st-s-run', Done: 'st-s-done', Stopped: 'st-s-stop' };

const RunsBoard = ({ liveEpoch, liveLoss }) => {
  const [open, setOpen] = useState(3);
  return (
    <ul className="st-runs" data-ui>
      {RUNS.map((run, i) => {
        const epoch = run.live ? `${liveEpoch}/90` : run.epoch;
        const loss = run.live ? liveLoss : run.loss;
        const detail = run.detail || `Epoch ${epoch}, loss ${loss}. Owned by ${run.owner}; its windows sit in the same workspace for everyone to open.`;
        return (
          <li key={run.name} className={`st-rise${open === i ? ' st-run-open' : ''}`}>
            <button type="button" aria-expanded={open === i} onClick={() => setOpen(i)}>
              <span>{run.name}</span>
              <span className="st-soft st-epoch">epoch {epoch}</span>
              <span className="st-soft st-loss">loss {loss}</span>
              <span className="st-soft st-owner">{run.owner}</span>
              <span className={`st-status ${STATUS_CLASS[run.status]}`}>{run.status}</span>
            </button>
            {open === i && <p className="st-detail">{detail}</p>}
          </li>
        );
      })}
    </ul>
  );
};

const FEATURES = [
  {
    title: 'Live plots, images and text',
    text: 'Line charts, scatter plots, heatmaps, images, audio and video, updated while the run is going.',
    fragment: (
      <div className="st-frag st-frag-shot" data-ui>
        <img src="/start/dashboard.png" alt="Loss, accuracy and learning rate plots in a Visdom environment" width="1400" height="967" loading="lazy" />
      </div>
    ),
  },
  {
    title: 'Workspaces and roles',
    text: 'One workspace per project. Admins manage it, members write to it, viewers only look.',
    fragment: (
      <div className="st-frag" data-ui>
        <table>
          <tbody>
            <tr><th>Member</th><th>Role</th></tr>
            <tr><td>ana@lab.org</td><td><span className="st-chip">Admin</span></td></tr>
            <tr><td>raj@lab.org</td><td><span className="st-chip">Member</span></td></tr>
            <tr><td>sam@lab.org</td><td><span className="st-chip">Viewer</span></td></tr>
          </tbody>
        </table>
      </div>
    ),
  },
  {
    title: 'Scoped API keys',
    text: 'Give each machine or pipeline its own key, set when it expires, and revoke it when you are done.',
    fragment: (
      <div className="st-frag" data-ui>
        <table>
          <tbody>
            <tr><th>Key</th><th>Reaches</th></tr>
            <tr><td>lab-gpu-01<br /><span className="st-chip">30 days left</span></td><td>resnet-sweeps</td></tr>
            <tr><td>ci-runner<br /><span className="st-chip">No expiry</span></td><td>All workspaces</td></tr>
          </tbody>
        </table>
      </div>
    ),
  },
  {
    title: 'Join links',
    text: 'Share one link to bring people in. Each person who opens it asks to join, and an admin approves them.',
    fragment: (
      <div className="st-frag" data-ui>
        {['priya@uni.edu', 'tom@lab.org', 'mei@uni.edu'].map((email) => (
          <div key={email} className="st-req">
            <span><b>{email}</b> asked to join resnet-sweeps</span>
            <span className="st-req-actions"><span className="st-mini">Approve</span><span className="st-mini st-mini-ghost">Decline</span></span>
          </div>
        ))}
      </div>
    ),
  },
  {
    title: 'Experiments and sweeps',
    text: 'Compare runs in the HParams dashboard, and log Optuna, PyTorch, Keras and XGBoost training as it happens.',
    fragment: (
      <div className="st-frag" data-ui>
        <table>
          <tbody>
            <tr><th>Trial</th><th>lr</th><th>batch</th><th>val acc</th></tr>
            <tr><td>15</td><td>1e-3</td><td>128</td><td>0.871</td></tr>
            <tr className="st-best"><td>17</td><td>3e-4</td><td>256</td><td>0.902</td></tr>
            <tr><td>16</td><td>1e-4</td><td>256</td><td>0.884</td></tr>
            <tr><td>18</td><td>3e-4</td><td>512</td><td>running</td></tr>
          </tbody>
        </table>
      </div>
    ),
  },
  {
    title: 'The client you already use',
    text: 'Keep your plotting code. Give the Visdom client a key and a workspace, and every call lands here.',
    fragment: (
      <div className="st-frag" data-ui>
        <pre className="st-code st-code-tall"><code>{`$ ${CLIENT_INSTALL}\n\nvis.line(Y=[loss], X=[step],\n         win="loss", update="append")\nvis.images(batch, win="samples")\nvis.text(notes, win="notes")`}</code></pre>
      </div>
    ),
  },
];

const Start = () => {
  const pageRef = useRef(null);
  useReveal(pageRef);
  const count = useLiveRun();
  const snippet = useMemo(() => plotSnippet(), []);
  const live = LIVE_TARGET.slice(0, count);
  const step = (count * 500).toLocaleString('en-US');
  const liveEpoch = Math.min(90, Math.round((count / LIVE_POINTS) * 90));
  const liveLoss = Math.max(0.3, LIVE_TARGET[count - 1] / 4.3 + 0.2).toFixed(3);

  return (
    <div className="st-page" ref={pageRef}>
      <header className="st-sheet">
        <div className="st-cols">
          <div className="st-col">
            <Pane title="val accuracy" tone="a" height={300}><Chart lines={CHARTS.acc} /></Pane>
            <Pane title="samples, epoch 41" tone="b"><Samples ids={[1025, 237, 1074, 433]} /></Pane>
            <Pane title="learning rate" tone="c" height={220}><Chart lines={CHARTS.lr} /></Pane>
          </div>
          <div className="st-col">
            <Pane title="confusion matrix" tone="d" height={260}><Heat seed={0} /></Pane>
            <Pane title="loss, resnet50-aug" tone="a" height={330}><Chart lines={CHARTS.loss2} /></Pane>
            <Pane title="notes" tone="b">
              <div className="st-textpane"><b>Run notes</b>Mixed precision on. Batch 256, cosine schedule, warmup 5 epochs. Validation every 500 steps.</div>
            </Pane>
          </div>
          <div className="st-pair">
            <div className="st-duo">
              <Pane title="gpu memory, GB" tone="c" height={150}><Chart lines={CHARTS.gpu} /></Pane>
              <Pane title="grad norm" tone="d" height={190}><Chart lines={CHARTS.grad} /></Pane>
            </div>
            <div className="st-pitch">
              <Link to="/" className="st-mark">
                <img src="/logo.svg" alt="" />
                <span>visdom</span>
              </Link>
              <h1>Watch training live, together.</h1>
              <p>Your plots, images and text in the browser while training runs. Hosted for your team, no server to set up.</p>
              <Link to="/register" className="st-btn">Get started</Link>
              <nav aria-label="Account">
                <Link to="/login">Sign in</Link>
                <a href={GITHUB_VISDOM}>GitHub</a>
              </nav>
            </div>
            <div className="st-duo">
              <Pane title="validation batch" tone="b"><Samples ids={[433, 659, 582, 1074]} /></Pane>
              <Pane title="val accuracy, vit-small" tone="a" height={300}><Chart lines={CHARTS.acc3} /></Pane>
            </div>
          </div>
          <div className="st-col">
            <Pane title="loss, resnet50-base" tone="b" height={360}>
              <span className="st-live"><b aria-hidden="true">●</b> live, step {step}</span>
              <Chart lines={[{ y: live, c: BLUE }]} range={LIVE_TARGET} slots={LIVE_POINTS} />
            </Pane>
            <Pane title="augmented batch" tone="a"><Samples ids={[582, 659, 237, 1025]} /></Pane>
            <Pane title="top-5 accuracy" tone="c" height={200}><Chart lines={CHARTS.acc2} /></Pane>
          </div>
          <div className="st-col">
            <Pane title="workspace" tone="d">
              <div className="st-textpane"><b>3 people watching</b>Ana, Raj and Sam have this environment open.</div>
            </Pane>
            <Pane title="loss, vit-small" tone="b" height={300}><Chart lines={CHARTS.loss3} /></Pane>
            <Pane title="attention, head 3" tone="a" height={260}><Heat seed={1} /></Pane>
          </div>
        </div>
      </header>

      <main>
        <section className="st-steps" aria-labelledby="st-how">
          <div className="st-field st-rise">
            <h2 id="st-how">From sign-up to first plot</h2>
            <div className="st-card" data-ui>
              <div className="st-row"><span className="st-big">resnet-sweeps</span><br /><span className="st-k">Workspace, created just now</span></div>
              <div className="st-row">1 member: you, admin</div>
            </div>
            <p className="st-clause">First you make a workspace.</p>
          </div>
          <div className="st-field st-rise">
            <div className="st-card" data-ui>
              <div className="st-row"><span className="st-big">lab-gpu-01</span><br /><span className="st-k">API key for resnet-sweeps</span></div>
              <div className="st-row">visdom_live_…3f9a<br /><span className="st-k">Expires in 30 days</span></div>
            </div>
            <p className="st-clause">Then you give your machine a key.</p>
          </div>
          <div className="st-field st-rise">
            <div className="st-card st-card-code" data-ui>
              <pre className="st-code"><code>{snippet}</code></pre>
            </div>
            <p className="st-clause">Then your script sends a plot.</p>
          </div>
          <div className="st-field st-rise">
            <div className="st-card" data-ui>
              <div className="st-row st-row-chart"><Chart lines={CHARTS.loss4} /></div>
              <div className="st-watchers">
                <i style={{ background: NAVY }}>A</i>
                <i style={{ background: BLUE }}>R</i>
                <i style={{ background: '#56688a' }}>S</i>
                <span className="st-k">watching</span>
              </div>
            </div>
            <p className="st-clause">And the whole team watches it grow.</p>
          </div>
        </section>

        <section className="st-board" aria-labelledby="st-runs">
          <h2 id="st-runs" className="st-rise">Every run, as it happens</h2>
          <RunsBoard liveEpoch={liveEpoch} liveLoss={liveLoss} />
        </section>

        <section className="st-features" aria-labelledby="st-get">
          <h2 id="st-get" className="st-rise">What you get</h2>
          <div className="st-cells">
            {FEATURES.map((feature) => (
              <div key={feature.title} className="st-cell st-rise">
                <div className="st-txt">
                  <h3>{feature.title}</h3>
                  <p>{feature.text}</p>
                </div>
                {feature.fragment}
              </div>
            ))}
          </div>
        </section>

        <section className="st-open" aria-labelledby="st-open-h">
          <figure className="st-open-pic st-rise">
            <img
              src="/start/fossasia-summit-2019.jpg"
              alt="Group photo of the FOSSASIA Summit 2019 at the Lifelong Learning Institute, Singapore"
              width="1600"
              height="737"
              loading="lazy"
            />
            <figcaption>FOSSASIA Summit 2019, Singapore</figcaption>
          </figure>
          <div className="st-open-txt st-rise">
            <h2 id="st-open-h">Built in the open</h2>
            <p>Visdom is open source and run by FOSSASIA. Want your own server instead? Install Visdom with pip and run it on your machine, the same as always.</p>
            <p>Everything behind visdom.dev is open source too.</p>
            <div className="st-open-links">
              <a href={GITHUB_VISDOM} className="st-btn st-btn-ink">fossasia/visdom</a>
              <a href={GITHUB_VISDOM_DEV} className="st-btn st-btn-ink">fossasia/visdom-dev</a>
            </div>
          </div>
        </section>

        <div className="st-cta-wrap">
          <section className="st-cta" aria-labelledby="st-cta-h">
            <div className="st-flank-l st-shutter">
              <img src="/start/dashboard.png" alt="A Visdom environment with loss, accuracy and learning rate plots" width="1400" height="967" loading="lazy" />
            </div>
            <div className="st-cta-main">
              <h2 id="st-cta-h">Your first plot in five minutes</h2>
              <p>Make an account, create a key and add a few lines to your training script.</p>
              <Link to="/register" className="st-btn st-btn-light">Create an account</Link>
            </div>
            <div className="st-flank-r" />
          </section>
        </div>
      </main>

      <footer className="st-footer">
        <div className="st-blocks" role="img" aria-label="visdom">
          {'visdom'.split('').map((letter, i) => (
            <span key={i} aria-hidden="true">{letter}</span>
          ))}
        </div>
        <div className="st-foot">
          <div>
            <h2>Product</h2>
            <Link to="/register">Get started</Link>
            <Link to="/login">Sign in</Link>
          </div>
          <div>
            <h2>Open source</h2>
            <a href={GITHUB_VISDOM}>fossasia/visdom</a>
            <a href={GITHUB_VISDOM_DEV}>fossasia/visdom-dev</a>
          </div>
          <div>
            <h2>Legal</h2>
            <Link to="/privacy">Privacy</Link>
            <Link to="/cookies">Cookies</Link>
          </div>
          <div className="st-contact">
            <h2>Contact</h2>
            <span>FOSSASIA</span>
            <a href="mailto:office@fossasia.org">office@fossasia.org</a>
          </div>
        </div>
        <div className="st-last">
          <span>
            Sample images from Unsplash via picsum.photos. Summit photo: &ldquo;FOSSASIA Summit 2019&rdquo; by Michael Cannon,{' '}
            <a href="https://creativecommons.org/licenses/by-sa/2.0">CC BY-SA 2.0</a>, via{' '}
            <a href="https://commons.wikimedia.org/wiki/File:FOSSASIA_Summit_2019.jpg">Wikimedia Commons</a>.
          </span>
          <Link to="/register" className="st-btn">Get started</Link>
        </div>
      </footer>
    </div>
  );
};

export default Start;
