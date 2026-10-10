/* Copyright 2017-present, The Visdom Authors */

export const CLIENT_INSTALL = 'pip install "git+https://github.com/vedansh-5/visdom.git@dev"';

export const KEY_PLACEHOLDER = 'visdom_live_...';

export const serverArgs = (location = window.location) => {
  const port = location.port || (location.protocol === 'https:' ? '443' : '80');
  return { server: `${location.protocol}//${location.hostname}`, port };
};

export const plotSnippet = ({ apiKey, workspace, location } = {}) => {
  const { server, port } = serverArgs(location);
  return [
    'import visdom',
    '',
    'vis = visdom.Visdom(',
    `    server="${server}", port=${port}, base_url="/vis",`,
    `    api_key="${apiKey || KEY_PLACEHOLDER}",`,
    `    workspace="${workspace || 'your-workspace'}",`,
    ')',
    '',
    'for step, loss in enumerate([0.9, 0.6, 0.4, 0.25]):',
    '    vis.line(X=[step], Y=[loss], win="loss", update="append",',
    '             env="experiment-1", opts={"title": "training loss"})',
  ].join('\n');
};
