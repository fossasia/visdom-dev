/* Copyright 2017-present, The Visdom Authors */
import { Link, useLocation } from 'react-router-dom';
import { UPDATED } from '../content/legal';

const LegalPage = ({ title, sections }) => {
  const location = useLocation();
  const kept = { from: location.state?.from };

  return (
    <div className="gc-legal-wrapper">
      <article className="gc-legal">
        <Link to={`/login${location.search}`} state={kept} className="gc-legal-back">Back to sign in</Link>
        <h1 className="gc-legal-title">{title}</h1>
        <p className="gc-legal-updated">Last updated {UPDATED}</p>
        {sections.map((section) => (
          <section key={section.heading}>
            <h2 className="gc-legal-heading">{section.heading}</h2>
            {section.body.map((line) => (
              <p key={line.slice(0, 40)} className="gc-legal-text">{line}</p>
            ))}
          </section>
        ))}
        <p className="gc-legal-text">
          <Link to={`/privacy${location.search}`} state={kept}>Privacy</Link>
          {' · '}
          <Link to={`/cookies${location.search}`} state={kept}>Cookies</Link>
        </p>
      </article>
    </div>
  );
};

export default LegalPage;
