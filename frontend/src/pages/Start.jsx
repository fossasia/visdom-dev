/* Copyright 2017-present, The Visdom Authors */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import StartHero from '../components/start/StartHero';
import Chart from '../components/start/Chart';
import { BLUE, CHARTS } from '../components/start/chartData';
import RunBrowser from '../components/start/RunBrowser';
import FeatureDemos from '../components/start/FeatureDemos';
import { copyToClipboard } from '../utils/clipboard';
import { plotSnippet } from '../utils/quickstart';
import '../css/start-sections.css';

const GITHUB_VISDOM = 'https://github.com/fossasia/visdom';
const GITHUB_VISDOM_DEV = 'https://github.com/fossasia/visdom-dev';

const FIRST_PLOT = [{ y: [0.9, 0.6, 0.4, 0.25], c: BLUE }];

const INSTALL = 'pip install visdom';

const Start = () => {
  const page = useRef(null);
  useEffect(() => {
    if (!window.IntersectionObserver) return;
    const root = page.current;
    const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const pending = new Set(root.querySelectorAll('[data-reveal]'));
    const observer = new IntersectionObserver(entries => {
      if (document.hidden || motion?.matches) return;
      for (const { target, isIntersecting } of entries) {
        if (isIntersecting && pending.delete(target)) {
          target.classList.add('st-entered');
          observer.unobserve(target);
        }
      }
    });
    const update = () => {
      observer.disconnect();
      if (document.hidden || motion?.matches) {
        root.querySelectorAll('.st-entered').forEach(element => element.classList.remove('st-entered'));
      } else {
        pending.forEach(element => observer.observe(element));
      }
    };
    update();
    motion?.addEventListener('change', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      observer.disconnect();
      motion?.removeEventListener('change', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, []);
  const [copyStatus, setCopyStatus] = useState('');
  const copyInstall = async () => {
    setCopyStatus(await copyToClipboard(INSTALL) ? 'Copied' : 'Select the command to copy it.');
  };
  return (
    <div className="st-page">
      <main ref={page}>
        <StartHero />
        <section className="st-steps" aria-labelledby="st-how">
          <div className="st-inner">
            <h2 data-reveal id="st-how">From sign-up to first plot</h2>
            <ol className="st-step-list">
              <li data-reveal className="st-field">
                <h3>Make a workspace.</h3>
                <div className="st-card">
                  <strong>resnet-sweeps</strong><span>Workspace, created just now</span>
                  <small>1 member · You, admin</small>
                </div>
              </li>
              <li data-reveal className="st-field">
                <h3>Give your machine a key.</h3>
                <div className="st-card">
                  <strong>lab-gpu-01</strong><span>Key for resnet-sweeps</span>
                  <small>Expires in 30 days</small>
                </div>
              </li>
              <li data-reveal className="st-field">
                <h3>Send a plot.</h3>
                <div className="st-card">
                  <code>vis.line(X=[step], Y=[loss])</code><span>Append a loss value at each step.</span>
                </div>
              </li>
              <li data-reveal className="st-field">
                <h3>Watch it with your team.</h3>
                <div className="st-team-preview">
                  <Chart label="Sample team training loss" lines={CHARTS.loss4} />
                  <div className="st-watchers">
                    <span aria-hidden="true"><i>A</i><i>R</i><i>S</i></span>
                    Ana, Raj and Sam watching
                  </div>
                </div>
              </li>
            </ol>
            <details data-reveal className="st-script">
              <summary>Show the complete Python example</summary>
              <pre className="st-code" tabIndex="0" aria-label="Connect your script to Visdom"><code>{plotSnippet()}</code></pre>
            </details>
          </div>
        </section>

        <RunBrowser />
        <FeatureDemos />

        <section className="st-open" aria-labelledby="st-open-h">
          <div className="st-inner st-open-layout">
            <div data-reveal>
              <h2 id="st-open-h">Built in the open</h2>
              <p>Visdom is open source and run by <a href="https://fossasia.org" rel="noopener">FOSSASIA</a>.
                {' '}Install it on your machine to run your own server.</p>
              <p>Everything behind visdom.dev is open source too.</p>
              <div className="st-open-links">
                <a href={GITHUB_VISDOM}>fossasia/visdom</a>
                <a href={GITHUB_VISDOM_DEV}>fossasia/visdom-dev</a>
              </div>
            </div>
            <div data-reveal className="st-install">
              <div className="st-demo-toolbar">
                <span>Install locally</span>
                <button type="button" aria-label="Copy install command" onClick={copyInstall}>Copy</button>
              </div>
              <pre className="st-code"><code>{INSTALL}</code></pre>
              <span role="status">{copyStatus}</span>
            </div>
          </div>
        </section>

        <section className="st-cta" aria-labelledby="st-cta-h">
          <div className="st-inner">
            <div data-reveal>
              <h2 id="st-cta-h">Your first plot in five minutes</h2>
              <p>Make an account, create a key and add a few lines to your training script.</p>
              <Link to="/register" className="st-btn">Create an account</Link>
            </div>
            <figure data-reveal className="st-preview-plot st-first-plot">
              <figcaption className="st-plot-title">Training loss <span>experiment-1</span></figcaption>
              <Chart label="Training loss from the example script" lines={FIRST_PLOT} drawOnEntry />
              <div className="st-plot-steps"><span>Step 0</span><span>Step 3</span></div>
            </figure>
          </div>
        </section>
      </main>

    </div>
  );
};

export default Start;
