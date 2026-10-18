/* Copyright 2017-present, The Visdom Authors */
import { Clock } from 'lucide-react';
import { expiringHeading, isExpiringSoon, retentionSummary } from '../../utils/retention';

const SHOWN = 5;

const RetentionBanner = ({ workspace, notice }) => {
  if (!workspace || !isExpiringSoon(notice)) return null;
  const count = notice.expiring.length;
  const rest = count - SHOWN;

  return (
    <section className="gc-panel gc-mb-lg">
      <div className="gc-panel-header">
        <span className="gc-panel-title">
          <Clock size={15} />
          &nbsp;{count === 1 ? '1 environment' : `${count} environments`} in {workspace.name} will be removed soon
        </span>
      </div>
      <div className="gc-row">
        <div className="gc-row-meta gc-retention-text">
          <div>{retentionSummary(notice)}</div>
          <div>{expiringHeading(notice)}</div>
          <div className="gc-retention-envs">
            {notice.expiring.slice(0, SHOWN).join(', ')}
            {rest > 0 && ` and ${rest} more`}
          </div>
        </div>
      </div>
    </section>
  );
};

export default RetentionBanner;
