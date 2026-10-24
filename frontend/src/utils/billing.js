/* Copyright 2017-present, The Visdom Authors */
export const formatMoment = (value) =>
  new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

export const isPaying = (billing) => Boolean(billing?.status);

export const subscriptionNote = (billing, planName) => {
  if (!isPaying(billing)) return null;
  if (billing.status === 'past_due') {
    return {
      tone: 'danger',
      text: `Your last payment for ${planName} did not go through. Update your card in Manage billing to keep the plan.`,
    };
  }
  if (billing.ends_at) {
    return { tone: 'muted', text: `Your ${planName} plan ends on ${formatMoment(billing.ends_at)} and will not renew.` };
  }
  if (billing.renews_at) {
    return { tone: 'muted', text: `Your ${planName} plan renews on ${formatMoment(billing.renews_at)}.` };
  }
  return { tone: 'muted', text: `You are on the ${planName} plan.` };
};

export const planAction = (plan, { currentTier, billing }) => {
  if (plan.id === currentTier) return { kind: 'current', label: 'Current Plan' };
  if (plan.price === null || plan.price === undefined) return { kind: 'contact', label: 'Contact us' };
  if (plan.price === 0) {
    return isPaying(billing)
      ? { kind: 'portal', label: 'Cancel in Manage billing' }
      : { kind: 'switch', label: `Switch to ${plan.name}` };
  }
  if (isPaying(billing)) return { kind: 'portal', label: 'Change in Manage billing' };
  if (plan.checkout) return { kind: 'checkout', label: `Upgrade to ${plan.name}` };
  return { kind: 'unavailable', label: 'Not available yet' };
};
