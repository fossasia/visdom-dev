/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ConfirmProvider, useConfirm } from '../ConfirmContext';

const TestApp = ({ onResult }) => {
  const confirm = useConfirm();

  const handleOpen = async () => {
    const res = await confirm({
      title: 'Delete this workspace?',
      message: 'All associated data will be removed.',
      confirmText: 'Delete',
      cancelText: 'Keep it',
      danger: true,
    });
    onResult(res);
  };

  return (
    <div>
      <button data-testid="trigger-btn" onClick={handleOpen} type="button">
        Trigger Confirm
      </button>
    </div>
  );
};

describe('ConfirmContext Accessibility & Dialog Behavior', () => {
  it('renders as a dialog with role="dialog", aria-modal="true", and accessible name', async () => {
    const user = userEvent.setup();
    render(
      <ConfirmProvider>
        <TestApp onResult={() => {}} />
      </ConfirmProvider>
    );

    await user.click(screen.getByTestId('trigger-btn'));

    const dialog = screen.getByRole('dialog', { name: 'Delete this workspace?' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('cancels the confirm dialog on Escape and restores focus to trigger', async () => {
    let result = null;
    const user = userEvent.setup();

    render(
      <ConfirmProvider>
        <TestApp onResult={(res) => { result = res; }} />
      </ConfirmProvider>
    );

    const trigger = screen.getByTestId('trigger-btn');
    await user.click(trigger);

    expect(screen.getByRole('dialog', { name: 'Delete this workspace?' })).toBeInTheDocument();

    await user.keyboard('{Escape}');

    expect(result).toBe(false);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('resolves true on clicking confirm', async () => {
    let result = null;
    const user = userEvent.setup();

    render(
      <ConfirmProvider>
        <TestApp onResult={(res) => { result = res; }} />
      </ConfirmProvider>
    );

    await user.click(screen.getByTestId('trigger-btn'));
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    expect(result).toBe(true);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('cancels the confirm dialog on overlay click', async () => {
    let result = null;
    const user = userEvent.setup();

    render(
      <ConfirmProvider>
        <TestApp onResult={(res) => { result = res; }} />
      </ConfirmProvider>
    );

    await user.click(screen.getByTestId('trigger-btn'));
    const dialog = screen.getByRole('dialog', { name: 'Delete this workspace?' });
    const overlay = dialog.closest('.gc-modal-overlay');

    await user.click(overlay);

    expect(result).toBe(false);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('supports input dialog and focuses the input element', async () => {
    let result = null;
    const user = userEvent.setup();

    const InputApp = () => {
      const confirm = useConfirm();
      return (
        <button
          data-testid="input-trigger"
          onClick={async () => {
            const res = await confirm({
              title: 'Enter workspace name',
              input: true,
              placeholder: 'Workspace Name',
            });
            result = res;
          }}
          type="button"
        >
          Prompt Name
        </button>
      );
    };

    render(
      <ConfirmProvider>
        <InputApp />
      </ConfirmProvider>
    );

    await user.click(screen.getByTestId('input-trigger'));

    const input = screen.getByPlaceholderText('Workspace Name');
    expect(input).toHaveFocus();

    await user.type(input, 'AI Studio');
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(result).toBe('AI Studio');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

