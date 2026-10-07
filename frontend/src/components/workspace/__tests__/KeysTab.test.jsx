/* Copyright 2017-present, The Visdom Authors */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  confirm: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
  copyToClipboard: vi.fn(),
  downloadTextFile: vi.fn(),
}));

vi.mock('../../../context/AuthContext', () => ({ api: mocks.api }));
vi.mock('../../../context/ConfirmContext', () => ({ useConfirm: () => mocks.confirm }));
vi.mock('../../toast/useToast', () => ({ useToast: () => mocks.toast }));
vi.mock('../../../utils/clipboard', () => ({
  copyToClipboard: mocks.copyToClipboard,
  downloadTextFile: mocks.downloadTextFile,
}));
vi.mock('../QuickStart', () => ({
  default: ({ apiKey, workspace }) => (
    <div data-testid="quickstart" data-key={apiKey || ''} data-workspace={workspace || ''} />
  ),
}));

import KeysTab from '../KeysTab';
import { clearRequestCache } from '../../../utils/requestCache';

const RAW_KEY = 'visdom_live_abcdef0123456789';

const WORKSPACES = [
  { id: 'ws-1', name: 'Alpha', slug: 'alpha' },
  { id: 'ws-2', name: 'Beta', slug: 'beta' },
];

const ORG_KEY = {
  id: 'key-1',
  name: 'laptop',
  prefix: 'visdom_live_abc123...',
  scope: 'org',
  workspaces: [],
  created_at: '2026-09-01T10:00:00Z',
  expires_at: null,
};

const SCOPED_KEY = {
  id: 'key-2',
  name: 'gpu-node',
  prefix: 'visdom_live_def456...',
  scope: 'workspace',
  workspaces: [{ id: 'ws-2', name: 'Beta', slug: 'beta' }],
  created_at: '2026-09-02T10:00:00Z',
  expires_at: '2020-01-01T00:00:00Z',
};

const listReturns = (...lists) => {
  lists.forEach((list) => mocks.api.get.mockResolvedValueOnce({ data: list }));
  mocks.api.get.mockResolvedValue({ data: lists[lists.length - 1] });
};

const renderTab = (props = {}) =>
  render(<KeysTab workspaces={WORKSPACES} activeWorkspace={WORKSPACES[0]} {...props} />);

const generate = async (user, name = 'ci-runner') => {
  await user.type(screen.getByPlaceholderText(/Key name/), name);
  await user.click(screen.getByRole('button', { name: /Generate/ }));
};

const newKeyBox = () => document.querySelector('.gc-form-success');

beforeEach(() => {
  vi.clearAllMocks();
  mocks.api.get.mockReset();
  clearRequestCache();
});

describe('KeysTab', () => {
  describe('the list', () => {
    it('says so when there are no keys', async () => {
      listReturns([]);
      renderTab();

      expect(await screen.findByText('No API keys generated yet.')).toBeInTheDocument();
      expect(screen.getByText('Active Keys (0)')).toBeInTheDocument();
    });

    it('shows each key with what it can reach and when it expires', async () => {
      listReturns([ORG_KEY, SCOPED_KEY]);
      renderTab();

      expect(await screen.findByText('Active Keys (2)')).toBeInTheDocument();

      const laptop = screen.getByText('laptop').closest('.gc-row');
      expect(within(laptop).getByText('All workspaces')).toBeInTheDocument();
      expect(within(laptop).getByText('Never expires')).toBeInTheDocument();
      expect(within(laptop).getByText(/visdom_live_abc123/)).toBeInTheDocument();

      const node = screen.getByText('gpu-node').closest('.gc-row');
      expect(within(node).getByText('Beta')).toBeInTheDocument();
      expect(within(node).getByText(/^Expired /)).toHaveClass('gc-badge-expired');
    });

    it('never shows a full key for one that already exists', async () => {
      listReturns([ORG_KEY]);
      renderTab();

      await screen.findByText('laptop');
      expect(newKeyBox()).toBeNull();
    });
  });

  describe('making a key', () => {
    it('asks for one that works everywhere by default', async () => {
      const user = userEvent.setup();
      listReturns([], [ORG_KEY]);
      mocks.api.post.mockResolvedValue({ data: { ...ORG_KEY, raw_key: RAW_KEY } });
      renderTab();

      await generate(user);

      expect(mocks.api.post).toHaveBeenCalledWith('/keys', {
        name: 'ci-runner',
        scope: 'org',
        workspace_ids: [],
        expires_at: null,
      });
    });

    it('shows the new key once and reloads the list', async () => {
      const user = userEvent.setup();
      listReturns([], [ORG_KEY]);
      mocks.api.post.mockResolvedValue({ data: { ...ORG_KEY, raw_key: RAW_KEY } });
      renderTab();

      await generate(user);

      expect(await screen.findByText(RAW_KEY)).toBeInTheDocument();
      expect(screen.getByText(/will not be shown to you again/)).toBeInTheDocument();
      expect(await screen.findByText('Active Keys (1)')).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/Key name/)).toHaveValue('');
    });

    it('hands the new key to the quick start for the workspace in view', async () => {
      const user = userEvent.setup();
      listReturns([]);
      mocks.api.post.mockResolvedValue({ data: { ...ORG_KEY, raw_key: RAW_KEY } });
      renderTab({ activeWorkspace: WORKSPACES[1] });

      await generate(user);
      await screen.findByText(RAW_KEY);

      const snippet = within(newKeyBox()).getByTestId('quickstart');
      expect(snippet).toHaveAttribute('data-key', RAW_KEY);
      expect(snippet).toHaveAttribute('data-workspace', 'beta');
    });

    it('sends the chosen expiry as a date', async () => {
      const user = userEvent.setup();
      listReturns([]);
      mocks.api.post.mockResolvedValue({ data: { ...ORG_KEY, raw_key: RAW_KEY } });
      renderTab();

      await user.selectOptions(screen.getByRole('combobox'), '30');
      await generate(user);

      const sent = mocks.api.post.mock.calls[0][1].expires_at;
      const days = (new Date(sent).getTime() - Date.now()) / 86400000;
      expect(days).toBeGreaterThan(27);
      expect(days).toBeLessThan(32);
    });

    it('refuses a restricted key with no workspace picked', async () => {
      const user = userEvent.setup();
      listReturns([]);
      renderTab();

      await user.click(screen.getByRole('radio', { name: /Only select workspaces/ }));
      await generate(user);

      expect(screen.getByText(/Select at least one workspace/)).toBeInTheDocument();
      expect(mocks.api.post).not.toHaveBeenCalled();
    });

    it('restricts a key to the workspaces picked', async () => {
      const user = userEvent.setup();
      listReturns([]);
      mocks.api.post.mockResolvedValue({ data: { ...SCOPED_KEY, raw_key: RAW_KEY } });
      renderTab();

      await user.click(screen.getByRole('radio', { name: /Only select workspaces/ }));
      await user.click(screen.getByRole('checkbox', { name: /Beta/ }));
      await generate(user);

      expect(mocks.api.post).toHaveBeenCalledWith(
        '/keys',
        expect.objectContaining({ scope: 'workspace', workspace_ids: ['ws-2'] })
      );
      await screen.findByText(RAW_KEY);
      expect(within(newKeyBox()).getByTestId('quickstart')).toHaveAttribute('data-workspace', 'beta');
    });

    it('shows why the server refused', async () => {
      const user = userEvent.setup();
      listReturns([]);
      mocks.api.post.mockRejectedValue({
        response: { data: { detail: 'You have reached the API key limit for the free plan.' } },
      });
      renderTab();

      await generate(user);

      expect(await screen.findByText(/reached the API key limit/)).toBeInTheDocument();
      expect(newKeyBox()).toBeNull();
    });
  });

  describe('the new key box', () => {
    const makeKey = async () => {
      const user = userEvent.setup();
      listReturns([]);
      mocks.api.post.mockResolvedValue({ data: { ...ORG_KEY, raw_key: RAW_KEY } });
      renderTab();
      await generate(user);
      await screen.findByText(RAW_KEY);
      return user;
    };

    it('copies the key', async () => {
      mocks.copyToClipboard.mockResolvedValue(true);
      const user = await makeKey();

      await user.click(screen.getByRole('button', { name: 'Copy key to clipboard' }));

      expect(mocks.copyToClipboard).toHaveBeenCalledWith(RAW_KEY);
      await waitFor(() => expect(mocks.toast.success).toHaveBeenCalledWith('API key copied to clipboard.'));
    });

    it('says so when the copy did not work', async () => {
      mocks.copyToClipboard.mockResolvedValue(false);
      const user = await makeKey();

      await user.click(screen.getByRole('button', { name: 'Copy key to clipboard' }));

      await waitFor(() => expect(mocks.toast.error).toHaveBeenCalled());
      expect(mocks.toast.success).not.toHaveBeenCalled();
    });

    it('downloads the key as a text file', async () => {
      mocks.downloadTextFile.mockReturnValue(true);
      const user = await makeKey();

      await user.click(screen.getByRole('button', { name: 'Download key as a text file' }));

      const [filename, contents] = mocks.downloadTextFile.mock.calls[0];
      expect(filename).toMatch(/^visdom-api-key-.*\.txt$/);
      expect(contents).toContain(RAW_KEY);
      expect(mocks.toast.success).toHaveBeenCalledWith('API key downloaded.');
    });

    it('takes the key off the page when closed', async () => {
      const user = await makeKey();

      await user.click(newKeyBox().querySelector('button'));

      expect(screen.queryByText(RAW_KEY)).not.toBeInTheDocument();
    });
  });

  describe('revoking', () => {
    it('does nothing when the confirmation is turned down', async () => {
      const user = userEvent.setup();
      listReturns([ORG_KEY]);
      mocks.confirm.mockResolvedValue(false);
      renderTab();

      await user.click(await screen.findByTitle('Revoke API Key'));

      expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({ danger: true }));
      expect(mocks.api.delete).not.toHaveBeenCalled();
      expect(screen.getByText('laptop')).toBeInTheDocument();
    });

    it('revokes the key and reloads the list once confirmed', async () => {
      const user = userEvent.setup();
      listReturns([ORG_KEY], []);
      mocks.confirm.mockResolvedValue(true);
      mocks.api.delete.mockResolvedValue({});
      renderTab();

      await user.click(await screen.findByTitle('Revoke API Key'));

      await waitFor(() => expect(mocks.api.delete).toHaveBeenCalledWith('/keys/key-1'));
      expect(await screen.findByText('No API keys generated yet.')).toBeInTheDocument();
      expect(mocks.toast.success).toHaveBeenCalledWith('API key revoked.');
    });

    it('keeps the key listed when the server refuses', async () => {
      const user = userEvent.setup();
      listReturns([ORG_KEY]);
      mocks.confirm.mockResolvedValue(true);
      mocks.api.delete.mockRejectedValue(new Error('nope'));
      renderTab();

      await user.click(await screen.findByTitle('Revoke API Key'));

      await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith('Failed to revoke API key.'));
      expect(screen.getByText('laptop')).toBeInTheDocument();
    });
  });
});
