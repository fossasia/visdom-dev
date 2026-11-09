/* Copyright 2017-present, The Visdom Authors */
import { Link, useLocation } from 'react-router-dom';

const NotFound = () => {
  const location = useLocation();

  return (
    <div className="gc-legal-wrapper">
      <article className="gc-legal">
        <h1 className="gc-legal-title">Page not found</h1>
        <p className="gc-legal-text">
          Nothing is served at {location.pathname}. Check the address, or head back to the console.
        </p>
        <Link to="/" className="gc-legal-back">
          Back to the console
        </Link>
      </article>
    </div>
  );
};

export default NotFound;
