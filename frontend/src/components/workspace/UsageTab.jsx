/* Copyright 2017-present, The Visdom Authors */
import { useCallback, useEffect, useState } from 'react';
import { Clock, HardDrive } from 'lucide-react';
import { api } from '../../context/AuthContext';
import { cachedGet } from '../../utils/requestCache';
import { parseApiError } from '../../utils/helpers';
import { formatActiveTime, formatBytes, monthLabel } from '../../utils/usageFormat';

const UsageTab = () => {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setUsage(await cachedGet('/usage', () => api.get('/usage').then((res) => res.data)));
    } catch (err) {
      setError(parseApiError(err, 'Could not load usage.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  if (loading) {
    return (
      <section className="gc-panel">
        <div className="gc-empty">Loading usage...</div>
      </section>
    );
  }

  const rows = usage?.workspaces || [];
  const totals = usage?.totals || { active_minutes: 0, storage_bytes: 0 };
  const cap = usage?.workspace_storage_limit ?? null;

  return (
    <div className="gc-flex-col-gap-lg">
      <section className="gc-panel">
        <div className="gc-panel-header">
          <span className="gc-panel-title">Usage in {monthLabel(usage?.period_start)}</span>
        </div>
        {error && <div className="gc-form-error">{error}</div>}

        <div className="gc-meter">
          <div className="gc-meter-label">
            <span>
              <Clock size={14} /> Active time
            </span>
            <span>{formatActiveTime(totals.active_minutes)}</span>
          </div>
        </div>
        <div className="gc-meter">
          <div className="gc-meter-label">
            <span>
              <HardDrive size={14} /> Storage
            </span>
            <span>{formatBytes(totals.storage_bytes)}</span>
          </div>
        </div>

        <div className="gc-text-desc-muted gc-mt-sm">
          Active time counts each minute in which one of your workspaces received at least one
          plot. A dashboard left open with nothing arriving does not count.
          {cap !== null &&
            ` Each workspace can hold up to ${formatBytes(cap)} of plots on your plan. Past that, new plots are refused until old environments are deleted.`}
        </div>
      </section>

      <section className="gc-panel">
        <div className="gc-panel-header">
          <span className="gc-panel-title">By workspace</span>
        </div>
        {rows.length === 0 ? (
          <div className="gc-empty">You don&apos;t own any workspaces yet.</div>
        ) : (
          rows.map((row) => (
            <div key={row.id} className="gc-meter">
              <div className="gc-meter-label">
                <span>{row.name}</span>
                <span>
                  {formatActiveTime(row.active_minutes)} &middot; {formatBytes(row.storage_bytes)}
                  {cap !== null && ` of ${formatBytes(cap)}`}
                </span>
              </div>
              {cap !== null && (
                <div className="gc-meter-track">
                  <div
                    className="gc-meter-fill"
                    style={{ width: `${Math.min(100, (row.storage_bytes / cap) * 100)}%` }}
                  />
                </div>
              )}
            </div>
          ))
        )}
      </section>
    </div>
  );
};

export default UsageTab;
