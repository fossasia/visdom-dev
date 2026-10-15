/* Copyright 2017-present, The Visdom Authors */

const PLAN_NAMES = {
  free: 'Free',
  pro: 'Pro',
  enterprise: 'Enterprise',
};

export const planName = (tier) => PLAN_NAMES[tier] || 'Free';

export const formatJoined = (value) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
};

export const formatLastSignIn = (value) => {
  if (!value) return 'This is your first sign-in';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.toLocaleDateString()} at ${date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })}`;
};
