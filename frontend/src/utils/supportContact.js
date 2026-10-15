/* Copyright 2017-present, The Visdom Authors */

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const supportHref = (contact, subject = 'Custom Visdom plan') => {
  const value = (contact || '').trim();
  if (!value) return null;
  if (/^https?:\/\//i.test(value)) return value;
  if (/^mailto:/i.test(value)) return value;
  if (EMAIL.test(value)) return `mailto:${value}?subject=${encodeURIComponent(subject)}`;
  return null;
};
