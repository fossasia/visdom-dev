/* Copyright 2017-present, The Visdom Authors */

export const formatActiveTime = (minutes) => {
  const total = Math.max(0, Math.round(Number(minutes) || 0));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours === 0) return `${rest}m`;
  if (rest === 0) return `${hours.toLocaleString()}h`;
  return `${hours.toLocaleString()}h ${rest}m`;
};

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'];

export const formatBytes = (bytes) => {
  let value = Math.max(0, Number(bytes) || 0);
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const shown = unit === 0 || value >= 100 ? Math.round(value) : value.toFixed(1);
  return `${shown} ${UNITS[unit]}`;
};

export const monthLabel = (iso) => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'This month';
  return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' });
};
