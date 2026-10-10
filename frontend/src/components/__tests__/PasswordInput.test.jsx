/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import PasswordInput from '../PasswordInput';

const field = () => document.querySelector('input');

describe('PasswordInput', () => {
  it('hides the password until asked', () => {
    render(<PasswordInput name="password" />);
    expect(field()).toHaveAttribute('type', 'password');
  });

  it('shows and hides the password on the toggle', async () => {
    const user = userEvent.setup();
    render(<PasswordInput name="password" />);

    await user.click(screen.getByRole('button', { name: 'Show password' }));
    expect(field()).toHaveAttribute('type', 'text');

    await user.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(field()).toHaveAttribute('type', 'password');
  });

  it('tells assistive tech which state it is in', async () => {
    const user = userEvent.setup();
    render(<PasswordInput name="password" />);

    const toggle = screen.getByRole('button');
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('test_password_reveal_control_is_keyboard_accessible', async () => {
    const user = userEvent.setup();
    render(<PasswordInput name="password" />);

    await user.tab();
    await user.tab();

    const toggle = screen.getByRole('button', { name: 'Show password' });
    expect(toggle).toHaveFocus();

    await user.keyboard('{Enter}');
    expect(field()).toHaveAttribute('type', 'text');

    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(field()).toHaveAttribute('type', 'password');
  });

  it('passes props through to the input', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <PasswordInput name="password" placeholder="Your password" onChange={onChange} />
    );

    await user.type(field(), 'hunter2');
    expect(field()).toHaveAttribute('placeholder', 'Your password');
    expect(onChange).toHaveBeenCalled();
  });

  it('keeps the class name it was given', () => {
    render(<PasswordInput className="custom-input" name="password" />);
    expect(field()).toHaveClass('custom-input', 'pw-field-input');
  });
});
