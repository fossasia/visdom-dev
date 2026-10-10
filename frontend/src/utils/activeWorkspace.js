/* Copyright 2017-present, The Visdom Authors */

export const WORKSPACE_QUERY_PARAM = 'workspace';

export const requestedWorkspaceSlug = (search) =>
  new URLSearchParams(search || '').get(WORKSPACE_QUERY_PARAM);

export const pickActiveWorkspace = (previous, workspaces, requestedSlug) => {
  const list = workspaces || [];

  if (previous) {
    return list.find((ws) => ws.id === previous.id) || null;
  }

  if (requestedSlug) {
    const requested = list.find((ws) => ws.slug === requestedSlug);
    if (requested) return requested;
  }

  return list[0] || null;
};
