/* Copyright 2017-present, The Visdom Authors */
import { AlertTriangle } from 'lucide-react';

const SuspendedBanner = ({ workspace }) => {
  if (!workspace || workspace.is_active !== false) return null;

  return (
    <section className="gc-panel gc-mb-lg">
      <div className="gc-panel-header">
        <span className="gc-panel-title">
          <AlertTriangle size={15} />
          &nbsp;{workspace.name} is suspended
        </span>
      </div>
      <div className="gc-row">
        <div className="gc-row-meta">
          Nothing has been deleted. Its plots and members are all still here, but
          it cannot be opened or written to until an administrator lifts the
          suspension. Contact one if you were not expecting this.
        </div>
      </div>
    </section>
  );
};

export default SuspendedBanner;
