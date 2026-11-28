/* Copyright 2017-present, The Visdom Authors */
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const NotFound = () => {
  const { user, loading } = useAuth();
  const location = useLocation();

  return (
    <div className="gc-legal-wrapper">
      <article className="gc-legal">
        <h1 className="gc-legal-title">Page not found</h1>
        <p className="gc-legal-text">
          Nothing is served at {location.pathname}. Check the address and try again.
        </p>
        {!loading && (
          <Link to="/" className="gc-legal-back">{user ? 'Open dashboard' : 'Back to home'}</Link>
        )}
      </article>
    </div>
  );
};

export default NotFound;
