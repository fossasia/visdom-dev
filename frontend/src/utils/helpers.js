/* Copyright 2017-present, The Visdom Authors */

export const ROLE_BADGE = {
  admin: 'gc-badge-admin',
  member: 'gc-badge-member',
  viewer: 'gc-badge-viewer',
};

export const parseApiError = (err, defaultMsg = 'An error occurred.') => {
  const detail = err.response?.data?.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg).join(', ');
  }
  return defaultMsg;
};

export const isAdminTarget = (path) => path === '/admin' || path.startsWith('/admin/');

const isSameOriginPath = (path) => /^\/(?![/\\])/.test(path);

export const resolvePostAuthTarget = (location) => {
  const next = new URLSearchParams(location.search).get('next');
  if (next && isSameOriginPath(next)) return next;
  return location.state?.from || '/';
};

export const redirectAfterAuth = (target, navigate) => {
  if (target.startsWith('/vis/') || isAdminTarget(target)) {
    window.location.assign(target);
    return;
  }
  navigate(target, { replace: true });
};

export const EXPIRY_PRESETS = [
  { value: 'none', label: 'No expiration' },
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '60', label: '60 days' },
  { value: '90', label: '90 days' },
  { value: 'custom', label: 'Custom...' },
];

export const resolveExpiresAt = (preset, customValue) => {
  if (preset === 'none') return null;
  if (preset === 'custom') {
    return customValue ? new Date(customValue).toISOString() : null;
  }
  const date = new Date();
  date.setDate(date.getDate() + parseInt(preset, 10));
  return date.toISOString();
};

export const describeExpiry = (expiresAt) => {
  if (!expiresAt) return { text: 'Never expires', isExpired: false };
  const date = new Date(expiresAt);
  const isExpired = date.getTime() < Date.now();
  return {
    text: `${isExpired ? 'Expired' : 'Expires'} ${date.toLocaleDateString()}`,
    isExpired,
  };
};
