/* Copyright 2017-present, The Visdom Authors */

import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import UsageTab from '../UsageTab';
import { clearRequestCache } from '../../../utils/requestCache';

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn() },
}));

vi.mock('../../../context/AuthContext', () => ({ api: mocks.api }));

describe('UsageTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearRequestCache();
  });

  const sampleUsage = {
    period_start: '2026-11-01T00:00:00Z',
    workspace_storage_limit: 1073741824, // 1.0 GB
    totals: {
      active_minutes: 125,
      storage_bytes: 524288000, // 500 MB
    },
    workspaces: [
      {
        id: 'ws-1',
        name: 'Vision Lab',
        active_minutes: 85,
        storage_bytes: 314572800, // 300 MB
      },
      {
        id: 'ws-2',
        name: 'NLP Core',
        active_minutes: 40,
        storage_bytes: 209715200, // 200 MB
      },
    ],
  };

  describe('loading state', () => {
    it('shows loading message while data is being fetched', () => {
      mocks.api.get.mockReturnValue(new Promise(() => {}));
      render(<UsageTab />);

      expect(screen.getByText('Loading usage...')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('displays error message when request fails with detail', async () => {
      mocks.api.get.mockRejectedValue({
        response: { data: { detail: 'Insufficient permissions to view usage.' } },
      });
      render(<UsageTab />);

      expect(await screen.findByText('Insufficient permissions to view usage.')).toBeInTheDocument();
    });

    it('displays fallback error message when request fails without detail', async () => {
      mocks.api.get.mockRejectedValue(new Error('Network offline'));
      render(<UsageTab />);

      expect(await screen.findByText('Could not load usage.')).toBeInTheDocument();
    });
  });

  describe('when usage data is loaded', () => {
    it('renders period header and overall totals with storage limit notice', async () => {
      mocks.api.get.mockResolvedValue({ data: sampleUsage });
      render(<UsageTab />);

      expect(await screen.findByText(/November 2026/)).toBeInTheDocument();
      expect(screen.getByText('Active time')).toBeInTheDocument();
      expect(screen.getByText('2h 5m')).toBeInTheDocument();
      expect(screen.getByText('Storage')).toBeInTheDocument();
      expect(screen.getByText('500 MB')).toBeInTheDocument();

      expect(
        screen.getByText(/Each workspace can hold up to 1\.0 GB of plots on your plan/)
      ).toBeInTheDocument();
    });

    it('renders fallback period label when period_start is invalid or missing', async () => {
      mocks.api.get.mockResolvedValue({
        data: {
          ...sampleUsage,
          period_start: 'invalid-date',
        },
      });
      render(<UsageTab />);

      expect(await screen.findByText(/Usage in This month/)).toBeInTheDocument();
    });

    it('omits storage limit notice when workspace_storage_limit is null (unlimited plan)', async () => {
      mocks.api.get.mockResolvedValue({
        data: {
          ...sampleUsage,
          workspace_storage_limit: null,
        },
      });
      render(<UsageTab />);

      await screen.findByText(/November 2026/);
      expect(
        screen.queryByText(/Each workspace can hold up to/)
      ).not.toBeInTheDocument();
    });

    it('shows empty message when user owns no workspaces', async () => {
      mocks.api.get.mockResolvedValue({
        data: {
          ...sampleUsage,
          workspaces: [],
        },
      });
      render(<UsageTab />);

      expect(await screen.findByText("You don't own any workspaces yet.")).toBeInTheDocument();
    });

    it('renders workspace breakdown with meters and progress bars when limit exists', async () => {
      mocks.api.get.mockResolvedValue({ data: sampleUsage });
      render(<UsageTab />);

      expect(await screen.findByText('Vision Lab')).toBeInTheDocument();
      const visionRow = screen.getByText('Vision Lab').closest('.gc-meter');
      expect(within(visionRow).getByText(/1h 25m/)).toBeInTheDocument();
      expect(within(visionRow).getByText(/300 MB/)).toBeInTheDocument();
      expect(within(visionRow).getByText(/of 1\.0 GB/)).toBeInTheDocument();

      const nlpRow = screen.getByText('NLP Core').closest('.gc-meter');
      expect(within(nlpRow).getByText(/40m/)).toBeInTheDocument();
      expect(within(nlpRow).getByText(/200 MB/)).toBeInTheDocument();
      expect(within(nlpRow).getByText(/of 1\.0 GB/)).toBeInTheDocument();

      const visionFill = visionRow.querySelector('.gc-meter-fill');
      expect(visionFill).toBeInTheDocument();
      expect(visionFill.style.width).toMatch(/^29\./);

      const nlpFill = nlpRow.querySelector('.gc-meter-fill');
      expect(nlpFill).toBeInTheDocument();
      expect(nlpFill.style.width).toMatch(/^19\./);
    });

    it('clamps meter fill at 100% when workspace exceeds storage limit', async () => {
      mocks.api.get.mockResolvedValue({
        data: {
          ...sampleUsage,
          workspaces: [
            {
              id: 'ws-over',
              name: 'Over Limit Lab',
              active_minutes: 10,
              storage_bytes: 2147483648, // 2.0 GB (over 1.0 GB limit)
            },
          ],
        },
      });
      render(<UsageTab />);

      expect(await screen.findByText('Over Limit Lab')).toBeInTheDocument();
      const row = screen.getByText('Over Limit Lab').closest('.gc-meter');
      expect(within(row).getByText(/10m/)).toBeInTheDocument();
      expect(within(row).getByText(/2\.0 GB/)).toBeInTheDocument();
      expect(within(row).getByText(/of 1\.0 GB/)).toBeInTheDocument();

      const fill = row.querySelector('.gc-meter-fill');
      expect(fill).toBeInTheDocument();
      expect(fill.style.width).toBe('100%');
    });

    it('renders workspace list without progress tracks when limit is null', async () => {
      mocks.api.get.mockResolvedValue({
        data: {
          ...sampleUsage,
          workspace_storage_limit: null,
        },
      });
      const { container } = render(<UsageTab />);

      expect(await screen.findByText('Vision Lab')).toBeInTheDocument();
      const row = screen.getByText('Vision Lab').closest('.gc-meter');
      expect(within(row).getByText(/1h 25m/)).toBeInTheDocument();
      expect(within(row).getByText(/300 MB/)).toBeInTheDocument();
      expect(within(row).queryByText(/of 1\.0 GB/)).not.toBeInTheDocument();

      expect(container.querySelectorAll('.gc-meter-track').length).toBe(0);
    });

    it('falls back to default zeroes when totals is missing', async () => {
      mocks.api.get.mockResolvedValue({
        data: {
          period_start: '2026-11-01T00:00:00Z',
          workspace_storage_limit: null,
          totals: null,
          workspaces: [],
        },
      });
      render(<UsageTab />);

      await screen.findByText(/November 2026/);
      expect(screen.getByText('0m')).toBeInTheDocument();
      expect(screen.getByText('0 B')).toBeInTheDocument();
    });
  });
});
