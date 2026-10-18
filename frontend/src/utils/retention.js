/* Copyright 2017-present, The Visdom Authors */
export const formatDay = (value) =>
  new Date(`${value}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

const planLabel = (notice) => (notice.plan ? `the owner's ${notice.plan} plan` : "the owner's plan");

export const retentionSummary = (notice) => {
  if (!notice) return null;
  const plan = planLabel(notice);
  switch (notice.state) {
    case 'forever':
      return `Every environment is kept for as long as the workspace exists, on ${plan}.`;
    case 'not_enforced':
      return `This workspace is on ${plan}, which keeps ${notice.days} days of history. Older environments are not being removed yet.`;
    case 'scheduled':
      return `From ${formatDay(notice.starts_on)}, environments not updated for ${notice.days} days will be removed, on ${plan}. The main environment is always kept.`;
    case 'active':
      return `Environments not updated for ${notice.days} days are removed, on ${plan}. The main environment is always kept.`;
    default:
      return null;
  }
};

export const expiringHeading = (notice) =>
  notice.state === 'scheduled'
    ? `These would go on ${formatDay(notice.starts_on)} unless they are updated before then:`
    : `These go within the next ${notice.warn_days} days unless they are updated:`;

export const isExpiringSoon = (notice) =>
  Boolean(notice && (notice.state === 'active' || notice.state === 'scheduled') && notice.expiring?.length);
