/* Copyright 2017-present, The Visdom Authors */
import { Link } from 'react-router-dom';
import { FlaskConical, Gift, Images, Key, Link2, Users } from 'lucide-react';
import { CLIENT_INSTALL, plotSnippet } from '../utils/quickstart';

const GITHUB_VISDOM = 'https://github.com/fossasia/visdom';
const GITHUB_VISDOM_DEV = 'https://github.com/fossasia/visdom-dev';

const STEPS = [
  {
    title: 'Make a workspace',
    text: 'Sign up and create a workspace for your project. Invite your team as admins, members or viewers.',
  },
  {
    title: 'Create an API key',
    text: 'A key can reach every workspace you belong to, or only the ones you pick.',
  },
  {
    title: 'Point your script at it',
    text: 'Add the key and the workspace to the Visdom client. Plots show up under Visualizations as they arrive.',
  },
];

const FEATURES = [
  {
    icon: Images,
    title: 'Live plots, images and text',
    text: 'Line charts, scatter plots, heatmaps, images, audio and video, updated while the run is going.',
  },
  {
    icon: Users,
    title: 'Workspaces and roles',
    text: 'One workspace per project. Admins manage it, members write to it, viewers only look.',
  },
  {
    icon: Key,
    title: 'Scoped API keys',
    text: 'Give each machine or pipeline its own key, set when it expires, and revoke it when you are done.',
  },
  {
    icon: Link2,
    title: 'Join links',
    text: 'Share one link to bring people in. Each person who opens it asks to join, and an admin approves them.',
  },
  {
    icon: FlaskConical,
    title: 'Experiments and sweeps',
    text: 'Compare runs in the HParams dashboard, and log Optuna, PyTorch, Keras and XGBoost training as it happens.',
  },
  {
    icon: Gift,
    title: 'Free to start',
    text: 'The free plan has a workspace and room for a small team. Upgrade when you need more.',
  },
];

const Start = () => (
  <div className="st-page">
    <header className="st-bar">
      <div className="st-bar-inner">
        <Link to="/" className="st-brand">
          <img src="/logo.svg" alt="" />
          <span>visdom</span>
        </Link>
        <nav className="st-bar-links">
          <a href={GITHUB_VISDOM}>GitHub</a>
          <Link to="/login">Sign in</Link>
          <Link to="/register" className="st-btn st-btn-primary st-btn-small">Get started</Link>
        </nav>
      </div>
    </header>

    <main>
      <section className="st-hero">
        <div className="st-hero-text">
          <h1>Watch your experiments live, together.</h1>
          <p className="st-lead">
            Visdom shows your plots, images and text in the browser while your training runs.
            Visdom Dev hosts it for your team, so there is no server to set up.
          </p>
          <div className="st-actions">
            <Link to="/register" className="st-btn st-btn-primary">Get started</Link>
            <Link to="/login" className="st-btn">Sign in</Link>
          </div>
          <p className="st-small">Free to start. Open source, built by FOSSASIA.</p>
        </div>
        <figure className="st-shot">
          <img src="/start/dashboard.png" alt="A Visdom environment with loss, accuracy and learning rate plots and a grid of sample images" />
        </figure>
      </section>

      <section className="st-section">
        <h2>Your first plot in three steps</h2>
        <div className="st-steps">
          <ol className="st-step-list">
            {STEPS.map((step, i) => (
              <li key={step.title}>
                <span className="st-step-num">{i + 1}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="st-code">
            <div className="gc-code">
              <div className="gc-code-head">Install the client</div>
              <pre className="gc-code-body">{CLIENT_INSTALL}</pre>
            </div>
            <div className="gc-code">
              <div className="gc-code-head">Send a plot</div>
              <pre className="gc-code-body">{plotSnippet()}</pre>
            </div>
          </div>
        </div>
      </section>

      <section className="st-section">
        <h2>What you get</h2>
        <div className="st-features">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="st-feature">
              <Icon size={20} className="st-feature-icon" aria-hidden="true" />
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="st-open">
        <h2>Built in the open</h2>
        <p>
          Visdom is open source and run by FOSSASIA. Want your own server instead? Install Visdom
          with pip and run it on your machine, the same as always. Everything behind visdom.dev is
          open source too.
        </p>
        <div className="st-actions st-actions-center">
          <a href={GITHUB_VISDOM} className="st-btn st-btn-light">fossasia/visdom</a>
          <a href={GITHUB_VISDOM_DEV} className="st-btn st-btn-light">fossasia/visdom-dev</a>
        </div>
      </section>
    </main>

    <footer className="st-footer">
      <Link to="/privacy">Privacy</Link>
      {' · '}
      <Link to="/cookies">Cookies</Link>
      {' · '}
      <a href={GITHUB_VISDOM_DEV}>GitHub</a>
    </footer>
  </div>
);

export default Start;
