/* Copyright 2017-present, The Visdom Authors */

export const apiErrorText = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item?.msg).filter(Boolean).join(', ') || fallback;
  }
  return fallback;
};

export const tokenFromHash = (hash) => new URLSearchParams((hash || '').replace(/^#/, '')).get('token') || '';
