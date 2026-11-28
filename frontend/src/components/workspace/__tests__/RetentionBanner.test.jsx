/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import RetentionBanner from '../RetentionBanner';

describe('RetentionBanner', () => {
  const sampleWorkspace = {
    id: 'ws-1',
    name: 'Vision Lab',
  };

  const sampleActiveNotice = {
    state: 'active',
    days: 30,
    warn_days: 7,
    plan: 'Pro',
    expiring: ['train-run-1', 'eval-run-2'],
  };

  describe('what it shows', () => {
    it('returns null when workspace is null, undefined, or omitted', () => {
      const { container: containerNull } = render(<RetentionBanner workspace={null} notice={sampleActiveNotice} />);
      expect(containerNull.firstChild).toBeNull();

      const { container: containerUndef } = render(<RetentionBanner workspace={undefined} notice={sampleActiveNotice} />);
      expect(containerUndef.firstChild).toBeNull();

      const { container: containerOmitted } = render(<RetentionBanner notice={sampleActiveNotice} />);
      expect(containerOmitted.firstChild).toBeNull();
    });

    it('returns null when notice is null or undefined', () => {
      const { container: containerNull } = render(<RetentionBanner workspace={sampleWorkspace} notice={null} />);
      expect(containerNull.firstChild).toBeNull();

      const { container: containerUndef } = render(<RetentionBanner workspace={sampleWorkspace} notice={undefined} />);
      expect(containerUndef.firstChild).toBeNull();
    });

    it('returns null when notice state is not expiring soon (forever or not_enforced)', () => {
      const foreverNotice = { state: 'forever', expiring: [] };
      const { container: containerForever } = render(<RetentionBanner workspace={sampleWorkspace} notice={foreverNotice} />);
      expect(containerForever.firstChild).toBeNull();

      const notEnforcedNotice = { state: 'not_enforced', expiring: [] };
      const { container: containerNotEnforced } = render(
        <RetentionBanner workspace={sampleWorkspace} notice={notEnforcedNotice} />
      );
      expect(containerNotEnforced.firstChild).toBeNull();
    });

    it('returns null when notice state is active but expiring list is empty', () => {
      const emptyExpiringNotice = { state: 'active', days: 30, warn_days: 7, expiring: [] };
      const { container } = render(<RetentionBanner workspace={sampleWorkspace} notice={emptyExpiringNotice} />);
      expect(container.firstChild).toBeNull();
    });

    it('renders singular environment heading and clock icon when exactly one environment is expiring', () => {
      const singleNotice = {
        state: 'active',
        days: 30,
        warn_days: 7,
        plan: 'Team',
        expiring: ['train-run-1'],
      };

      const { container } = render(<RetentionBanner workspace={sampleWorkspace} notice={singleNotice} />);

      expect(screen.getByText(/1 environment in Vision Lab will be removed soon/)).toBeInTheDocument();
      expect(screen.getByText('train-run-1')).toBeInTheDocument();
      expect(screen.queryByText(/and \d+ more/)).not.toBeInTheDocument();
      const icon = container.querySelector('.gc-panel-title svg');
      expect(icon).toBeInTheDocument();
      expect(icon).toHaveClass('lucide-clock');
    });

    it('renders plural environments heading when multiple environments are expiring', () => {
      render(<RetentionBanner workspace={sampleWorkspace} notice={sampleActiveNotice} />);

      expect(screen.getByText(/2 environments in Vision Lab will be removed soon/)).toBeInTheDocument();
      expect(screen.getByText('train-run-1, eval-run-2')).toBeInTheDocument();
      expect(screen.queryByText(/and \d+ more/)).not.toBeInTheDocument();
    });

    it('displays all environments without truncation when count equals display limit of 5', () => {
      const fiveNotice = {
        state: 'active',
        days: 30,
        warn_days: 7,
        plan: 'Team',
        expiring: ['env-1', 'env-2', 'env-3', 'env-4', 'env-5'],
      };

      render(<RetentionBanner workspace={sampleWorkspace} notice={fiveNotice} />);

      expect(screen.getByText(/5 environments in Vision Lab will be removed soon/)).toBeInTheDocument();
      expect(screen.getByText('env-1, env-2, env-3, env-4, env-5')).toBeInTheDocument();
      expect(screen.queryByText(/and \d+ more/)).not.toBeInTheDocument();
    });

    it('displays retention summary and warning days heading for active notices', () => {
      render(<RetentionBanner workspace={sampleWorkspace} notice={sampleActiveNotice} />);

      expect(
        screen.getByText(
          "Environments not updated for 30 days are removed, on the owner's Pro plan. The main environment is always kept."
        )
      ).toBeInTheDocument();
      expect(
        screen.getByText('These go within the next 7 days unless they are updated:')
      ).toBeInTheDocument();
    });

    it('displays scheduled date summary and scheduled heading for scheduled notices', () => {
      const scheduledNotice = {
        state: 'scheduled',
        starts_on: '2026-12-01',
        days: 14,
        plan: 'Free',
        expiring: ['old-model'],
      };

      render(<RetentionBanner workspace={sampleWorkspace} notice={scheduledNotice} />);

      expect(
        screen.getByText(
          "From 1 December 2026, environments not updated for 14 days will be removed, on the owner's Free plan. The main environment is always kept."
        )
      ).toBeInTheDocument();
      expect(
        screen.getByText('These would go on 1 December 2026 unless they are updated before then:')
      ).toBeInTheDocument();
    });

    it('truncates environment list and shows "and X more" when expiring count exceeds 5', () => {
      const manyNotice = {
        state: 'active',
        days: 30,
        warn_days: 5,
        plan: 'Pro',
        expiring: ['env-1', 'env-2', 'env-3', 'env-4', 'env-5', 'env-6', 'env-7', 'env-8'],
      };

      render(<RetentionBanner workspace={sampleWorkspace} notice={manyNotice} />);

      expect(screen.getByText(/8 environments in Vision Lab will be removed soon/)).toBeInTheDocument();
      expect(screen.getByText(/env-1, env-2, env-3, env-4, env-5/)).toBeInTheDocument();
      expect(screen.getByText(/and 3 more/)).toBeInTheDocument();
      expect(screen.queryByText(/env-6/)).not.toBeInTheDocument();
    });
  });
});
