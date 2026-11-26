/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SuspendedBanner from '../SuspendedBanner';

describe('SuspendedBanner', () => {
  describe('what it shows', () => {
    it('returns null when workspace is null or undefined', () => {
      const { container: containerNull } = render(<SuspendedBanner workspace={null} />);
      expect(containerNull.firstChild).toBeNull();

      const { container: containerUndef } = render(<SuspendedBanner workspace={undefined} />);
      expect(containerUndef.firstChild).toBeNull();
    });

    it('returns null when workspace is active (is_active is true)', () => {
      const activeWorkspace = {
        id: 'ws-1',
        name: 'Active Research Lab',
        is_active: true,
      };

      const { container } = render(<SuspendedBanner workspace={activeWorkspace} />);
      expect(container.firstChild).toBeNull();
    });

    it('returns null when workspace is_active property is omitted or undefined', () => {
      const unspecifiedWorkspace = {
        id: 'ws-2',
        name: 'Unspecified Lab',
      };

      const { container } = render(<SuspendedBanner workspace={unspecifiedWorkspace} />);
      expect(container.firstChild).toBeNull();
    });

    it('renders the suspended banner with workspace name and warning icon when is_active is false', () => {
      const suspendedWorkspace = {
        id: 'ws-3',
        name: 'Bioinformatics Lab',
        is_active: false,
      };

      render(<SuspendedBanner workspace={suspendedWorkspace} />);

      expect(screen.getByText(/Bioinformatics Lab is suspended/)).toBeInTheDocument();
      expect(
        screen.getByText(
          /Nothing has been deleted\. Its plots and members are all still here, but it cannot be opened or written to until an administrator lifts the suspension\. Contact one if you were not expecting this\./
        )
      ).toBeInTheDocument();
    });
  });
});
