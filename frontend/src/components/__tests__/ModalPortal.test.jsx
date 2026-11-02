/* Copyright 2017-present, The Visdom Authors */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import ModalPortal from '../ModalPortal';

describe('ModalPortal Accessibility & Dialog Behavior', () => {
  it('has role="dialog", aria-modal="true", and accessible name via aria-labelledby', () => {
    render(
      <ModalPortal onClose={() => {}} aria-labelledby="modal-test-title">
        <div className="gc-modal-header">
          <span id="modal-test-title" className="gc-modal-title">
            Test Dialog Title
          </span>
          <button className="gc-modal-close" type="button" aria-label="Close">
            X
          </button>
        </div>
      </ModalPortal>
    );

    const dialog = screen.getByRole('dialog', { name: 'Test Dialog Title' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'modal-test-title');
  });

  it('supports direct accessible name via aria-label', () => {
    render(
      <ModalPortal onClose={() => {}} aria-label="Direct Accessible Name">
        <p>Modal content</p>
      </ModalPortal>
    );

    const dialog = screen.getByRole('dialog', { name: 'Direct Accessible Name' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-label', 'Direct Accessible Name');
  });

  it('auto-detects visible .gc-modal-title when no explicit label is provided', () => {
    render(
      <ModalPortal onClose={() => {}}>
        <div className="gc-modal-header">
          <span className="gc-modal-title">Auto Discovered Title</span>
        </div>
      </ModalPortal>
    );

    const dialog = screen.getByRole('dialog', { name: 'Auto Discovered Title' });
    expect(dialog).toBeInTheDocument();
  });

  it('moves initial focus to the first focusable element when no autoFocus exists', () => {
    render(
      <ModalPortal onClose={() => {}} aria-label="Initial Focus Test">
        <button type="button" data-testid="first-btn">
          First Button
        </button>
        <button type="button" data-testid="second-btn">
          Second Button
        </button>
      </ModalPortal>
    );

    expect(screen.getByTestId('first-btn')).toHaveFocus();
  });

  it('prefers an existing autoFocus element over the first focusable element', () => {
    render(
      <ModalPortal onClose={() => {}} aria-label="AutoFocus Preference Test">
        <button type="button" data-testid="close-btn" aria-label="Close">
          X
        </button>
        <input type="text" data-testid="name-input" autoFocus placeholder="Enter name" />
      </ModalPortal>
    );

    expect(screen.getByTestId('name-input')).toHaveFocus();
  });

  it('wraps Tab navigation from the last element to the first element', async () => {
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={() => {}} aria-label="Tab Wrap Test">
        <button type="button" data-testid="btn-1">
          First
        </button>
        <button type="button" data-testid="btn-2">
          Second
        </button>
        <button type="button" data-testid="btn-3">
          Last
        </button>
      </ModalPortal>
    );

    // Initial focus is on the first button
    expect(screen.getByTestId('btn-1')).toHaveFocus();

    // Tab to second button
    await user.tab();
    expect(screen.getByTestId('btn-2')).toHaveFocus();

    // Tab to last button
    await user.tab();
    expect(screen.getByTestId('btn-3')).toHaveFocus();

    // Tab on the last element wraps back to the first element
    await user.tab();
    expect(screen.getByTestId('btn-1')).toHaveFocus();
  });

  it('wraps Shift+Tab navigation from the first element to the last element', async () => {
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={() => {}} aria-label="Shift+Tab Wrap Test">
        <button type="button" data-testid="btn-1">
          First
        </button>
        <button type="button" data-testid="btn-2">
          Second
        </button>
        <button type="button" data-testid="btn-3">
          Last
        </button>
      </ModalPortal>
    );

    // Initial focus on first button
    expect(screen.getByTestId('btn-1')).toHaveFocus();

    // Shift+Tab from first element wraps to the last element
    await user.tab({ shift: true });
    expect(screen.getByTestId('btn-3')).toHaveFocus();

    // Shift+Tab from last element goes to second element
    await user.tab({ shift: true });
    expect(screen.getByTestId('btn-2')).toHaveFocus();
  });

  it('closes a dismissible modal when Escape is pressed', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={handleClose} aria-label="Escape Test">
        <button type="button">Close</button>
      </ModalPortal>
    );

    await user.keyboard('{Escape}');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('does not close on Escape when closeOnEscape is false', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={handleClose} closeOnEscape={false} aria-label="No Escape Test">
        <button type="button">Action</button>
      </ModalPortal>
    );

    await user.keyboard('{Escape}');
    expect(handleClose).not.toHaveBeenCalled();
  });

  it('restores focus to the opener element when the modal closes', async () => {
    const user = userEvent.setup();

    const TestComponent = () => {
      const [open, setOpen] = useState(false);

      return (
        <div>
          <button data-testid="opener-btn" onClick={() => setOpen(true)} type="button">
            Open Modal
          </button>
          {open && (
            <ModalPortal onClose={() => setOpen(false)} aria-label="Restoration Test">
              <button data-testid="inside-btn" onClick={() => setOpen(false)} type="button">
                Close Modal
              </button>
            </ModalPortal>
          )}
        </div>
      );
    };

    render(<TestComponent />);

    const openerBtn = screen.getByTestId('opener-btn');
    openerBtn.focus();
    expect(openerBtn).toHaveFocus();

    // Open the modal by clicking opener
    await user.click(openerBtn);

    // Focus moved inside modal
    expect(screen.getByTestId('inside-btn')).toHaveFocus();

    // Close the modal
    await user.click(screen.getByTestId('inside-btn'));

    // Focus is restored to the opener button
    expect(openerBtn).toHaveFocus();
  });

  it('does not close when clicking inside the dialog panel', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={handleClose} aria-label="Inside Click Test">
        <div data-testid="panel-content">
          <h3>Modal Header</h3>
          <p>Dialog body text</p>
        </div>
      </ModalPortal>
    );

    await user.click(screen.getByTestId('panel-content'));
    expect(handleClose).not.toHaveBeenCalled();
  });

  it('closes when clicking on the modal overlay backdrop', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={handleClose} aria-label="Overlay Click Test">
        <p>Dialog content</p>
      </ModalPortal>
    );

    const overlay = document.querySelector('.gc-modal-overlay');
    expect(overlay).toBeInTheDocument();

    await user.click(overlay);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('handles modals with no focusable elements correctly', async () => {
    const handleClose = vi.fn();
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={handleClose} aria-label="Empty Modal">
        <p>This modal has only static text and no buttons, inputs, or links.</p>
      </ModalPortal>
    );

    const dialog = screen.getByRole('dialog', { name: 'Empty Modal' });

    // Initial focus lands on the dialog container itself
    expect(dialog).toHaveFocus();

    // Tab key does not escape dialog
    await user.tab();
    expect(dialog).toHaveFocus();

    // Shift+Tab key also does not escape dialog
    await user.tab({ shift: true });
    expect(dialog).toHaveFocus();

    // Escape key still works to close the modal
    await user.keyboard('{Escape}');
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('handles nested modals properly: top modal handles Escape and traps focus', async () => {
    const handleCloseA = vi.fn();
    const handleCloseB = vi.fn();
    const user = userEvent.setup();

    const NestedModals = () => {
      const [showModalB, setShowModalB] = useState(false);

      return (
        <ModalPortal onClose={handleCloseA} aria-label="Modal A">
          <button data-testid="modal-a-btn-1" type="button">
            Modal A First
          </button>
          <button
            data-testid="open-modal-b-btn"
            onClick={() => setShowModalB(true)}
            type="button"
          >
            Open Modal B
          </button>
          {showModalB && (
            <ModalPortal
              onClose={() => {
                handleCloseB();
                setShowModalB(false);
              }}
              aria-label="Modal B"
            >
              <button data-testid="modal-b-btn-1" type="button">
                Modal B Content
              </button>
            </ModalPortal>
          )}
        </ModalPortal>
      );
    };

    render(<NestedModals />);

    // Focus is initially inside Modal A
    expect(screen.getByTestId('modal-a-btn-1')).toHaveFocus();

    // Click button to open Modal B
    await user.click(screen.getByTestId('open-modal-b-btn'));

    // Focus moves inside Modal B
    expect(screen.getByTestId('modal-b-btn-1')).toHaveFocus();

    // Pressing Escape should only close Modal B, NOT Modal A
    await user.keyboard('{Escape}');
    expect(handleCloseB).toHaveBeenCalledTimes(1);
    expect(handleCloseA).not.toHaveBeenCalled();

    // Focus returns to the button in Modal A that opened Modal B
    expect(screen.getByTestId('open-modal-b-btn')).toHaveFocus();

    // Pressing Escape again closes Modal A
    await user.keyboard('{Escape}');
    expect(handleCloseA).toHaveBeenCalledTimes(1);
  });

  it('excludes hidden, aria-hidden, inert, disabled, and CSS-hidden elements from focus order', async () => {
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={() => {}} aria-label="Visibility and Disabled Test">
        {/* Valid first button */}
        <button type="button" data-testid="btn-valid-1">Valid 1</button>

        {/* HTML hidden attribute on element and container */}
        <button type="button" hidden data-testid="btn-hidden">Hidden</button>
        <div hidden>
          <button type="button" data-testid="btn-inside-hidden">Inside Hidden</button>
        </div>

        {/* aria-hidden="true" container */}
        <div aria-hidden="true">
          <button type="button" data-testid="btn-aria-hidden">Aria Hidden</button>
        </div>

        {/* inert container */}
        <div inert={true}>
          <button type="button" data-testid="btn-inert">Inert</button>
        </div>

        {/* display: none directly and on container */}
        <button type="button" style={{ display: 'none' }} data-testid="btn-display-none">Display None</button>
        <div style={{ display: 'none' }}>
          <button type="button" data-testid="btn-inside-display-none">Inside Display None</button>
        </div>

        {/* visibility: hidden and collapse */}
        <button type="button" style={{ visibility: 'hidden' }} data-testid="btn-visibility-hidden">Vis Hidden</button>
        <button type="button" style={{ visibility: 'collapse' }} data-testid="btn-visibility-collapse">Vis Collapse</button>

        {/* Disabled control and fieldset disabled */}
        <button type="button" disabled data-testid="btn-disabled">Disabled</button>
        <fieldset disabled>
          <button type="button" data-testid="btn-fieldset-disabled">Fieldset Disabled</button>
        </fieldset>

        {/* Legend inside disabled fieldset remains enabled */}
        <fieldset disabled>
          <legend>
            <button type="button" data-testid="btn-legend-enabled">Legend Enabled</button>
          </legend>
          <button type="button" data-testid="btn-fieldset-disabled-2">Fieldset Disabled 2</button>
        </fieldset>

        {/* tabindex="-1" */}
        <button type="button" tabIndex={-1} data-testid="btn-tabindex-neg">Tabindex Neg</button>

        {/* Legitimate focusable elements: link with href, select, textarea, contenteditable, iframe */}
        <a href="#test" data-testid="link-enabled">Link</a>
        <select data-testid="select-enabled"><option>Option</option></select>
        <textarea data-testid="textarea-enabled" defaultValue="Text" />
        <div contentEditable="true" suppressContentEditableWarning data-testid="contenteditable-enabled">Edit me</div>
        <button type="button" data-testid="btn-valid-last">Valid Last</button>
        <iframe title="Test frame" data-testid="iframe-enabled" tabIndex={0} />
      </ModalPortal>
    );

    // Initial focus lands on the first valid button
    expect(screen.getByTestId('btn-valid-1')).toHaveFocus();

    // Tab jumps over all hidden/disabled elements directly to the enabled legend button
    await user.tab();
    expect(screen.getByTestId('btn-legend-enabled')).toHaveFocus();

    // Tab to link
    await user.tab();
    expect(screen.getByTestId('link-enabled')).toHaveFocus();

    // Tab to select
    await user.tab();
    expect(screen.getByTestId('select-enabled')).toHaveFocus();

    // Tab to textarea
    await user.tab();
    expect(screen.getByTestId('textarea-enabled')).toHaveFocus();

    // Tab to contenteditable
    await user.tab();
    expect(screen.getByTestId('contenteditable-enabled')).toHaveFocus();

    // Tab to valid last button
    await user.tab();
    expect(screen.getByTestId('btn-valid-last')).toHaveFocus();

    // Tab to iframe (verifies iframe is recognized as legitimate focusable element)
    await user.tab();
    expect(screen.getByTestId('iframe-enabled')).toHaveFocus();
  });

  it('restores focus into the dialog if focus is programmatically moved outside', () => {
    render(
      <div>
        <button data-testid="external-btn" type="button">
          Outside Button
        </button>
        <ModalPortal onClose={() => {}} aria-label="Programmatic Focus Test">
          <button data-testid="inside-btn" type="button">
            Inside Button
          </button>
        </ModalPortal>
      </div>
    );

    expect(screen.getByTestId('inside-btn')).toHaveFocus();

    // Programmatically try to move focus outside
    const externalBtn = screen.getByTestId('external-btn');
    externalBtn.focus();

    // Focusin handler immediately restores focus to the dialog
    expect(screen.getByTestId('inside-btn')).toHaveFocus();
  });

  it('handles a focused element becoming disabled or hidden during interaction', async () => {
    const user = userEvent.setup();

    const DynamicComponent = () => {
      const [disabled, setDisabled] = useState(false);
      return (
        <ModalPortal onClose={() => {}} aria-label="Dynamic State Test">
          <button
            data-testid="toggle-btn"
            type="button"
            disabled={disabled}
            onClick={() => setDisabled(true)}
          >
            {disabled ? 'Disabled' : 'Disable Me'}
          </button>
          <button data-testid="fallback-btn" type="button">
            Fallback Button
          </button>
        </ModalPortal>
      );
    };

    render(<DynamicComponent />);

    const toggleBtn = screen.getByTestId('toggle-btn');
    expect(toggleBtn).toHaveFocus();

    // Click to disable the active button
    await user.click(toggleBtn);
    expect(toggleBtn).toBeDisabled();

    // Pressing Tab should seamlessly move to the next valid focusable element
    await user.tab();
    expect(screen.getByTestId('fallback-btn')).toHaveFocus();
  });

  it('dynamically adapts to elements added or removed in the modal', async () => {
    const user = userEvent.setup();

    const DynamicListModal = () => {
      const [showExtra, setShowExtra] = useState(false);
      return (
        <ModalPortal onClose={() => {}} aria-label="Dynamic List Test">
          <button data-testid="first-btn" type="button">
            First
          </button>
          <button
            data-testid="add-btn"
            type="button"
            onClick={() => setShowExtra(true)}
          >
            Add Field
          </button>
          {showExtra && (
            <input data-testid="dynamic-input" type="text" placeholder="Extra" />
          )}
          <button data-testid="last-btn" type="button">
            Last
          </button>
        </ModalPortal>
      );
    };

    render(<DynamicListModal />);

    expect(screen.getByTestId('first-btn')).toHaveFocus();

    // Add extra field
    await user.tab();
    expect(screen.getByTestId('add-btn')).toHaveFocus();
    await user.click(screen.getByTestId('add-btn'));

    // Tab to the newly added dynamic input
    await user.tab();
    expect(screen.getByTestId('dynamic-input')).toHaveFocus();

    // Tab to last
    await user.tab();
    expect(screen.getByTestId('last-btn')).toHaveFocus();

    // Tab wraps to first
    await user.tab();
    expect(screen.getByTestId('first-btn')).toHaveFocus();
  });

  it('keeps focus on the single element when the dialog has only one focusable element', async () => {
    const user = userEvent.setup();

    render(
      <ModalPortal onClose={() => {}} aria-label="Single Focusable Test">
        <p>Information text</p>
        <button data-testid="lone-btn" type="button">
          Only Button
        </button>
      </ModalPortal>
    );

    const loneBtn = screen.getByTestId('lone-btn');
    expect(loneBtn).toHaveFocus();

    // Tab stays on the only button
    await user.tab();
    expect(loneBtn).toHaveFocus();

    // Shift+Tab stays on the only button
    await user.tab({ shift: true });
    expect(loneBtn).toHaveFocus();
  });

  it('prevents parent modal from closing when clicking parent backdrop while child modal is open', async () => {
    const handleCloseParent = vi.fn();
    const handleCloseChild = vi.fn();
    const user = userEvent.setup();

    const NestedBackdropTest = () => {
      const [childOpen, setChildOpen] = useState(true);

      return (
        <ModalPortal onClose={handleCloseParent} aria-label="Parent Modal">
          <button data-testid="parent-trigger" type="button">
            Parent Button
          </button>
          {childOpen && (
            <ModalPortal
              onClose={() => {
                handleCloseChild();
                setChildOpen(false);
              }}
              aria-label="Child Modal"
            >
              <button data-testid="child-btn" type="button">
                Child Button
              </button>
            </ModalPortal>
          )}
        </ModalPortal>
      );
    };

    render(<NestedBackdropTest />);

    const parentDialog = screen.getByRole('dialog', { name: 'Parent Modal' });
    const childDialog = screen.getByRole('dialog', { name: 'Child Modal' });

    const parentOverlay = parentDialog.closest('.gc-modal-overlay');
    const childOverlay = childDialog.closest('.gc-modal-overlay');

    // Clicking parent overlay while child modal is open must NOT close parent modal
    await user.click(parentOverlay);
    expect(handleCloseParent).not.toHaveBeenCalled();
    expect(handleCloseChild).not.toHaveBeenCalled();

    // Clicking child overlay closes only the child modal
    await user.click(childOverlay);
    expect(handleCloseChild).toHaveBeenCalledTimes(1);
    expect(handleCloseParent).not.toHaveBeenCalled();

    // Now that child modal is closed, clicking parent overlay closes parent modal
    await user.click(parentOverlay);
    expect(handleCloseParent).toHaveBeenCalledTimes(1);
  });

  it('handles opener element removed from DOM safely without crashing', async () => {
    const user = userEvent.setup();

    const RemovedOpenerComponent = () => {
      const [showOpener, setShowOpener] = useState(true);
      const [modalOpen, setModalOpen] = useState(false);

      return (
        <div>
          {showOpener && (
            <button
              data-testid="temporary-opener"
              onClick={() => {
                setModalOpen(true);
                setShowOpener(false); // Opener disappears from DOM
              }}
              type="button"
            >
              Open and Disappear
            </button>
          )}
          {modalOpen && (
            <ModalPortal onClose={() => setModalOpen(false)} aria-label="Removed Opener Test">
              <button
                data-testid="close-btn"
                onClick={() => setModalOpen(false)}
                type="button"
              >
                Close
              </button>
            </ModalPortal>
          )}
        </div>
      );
    };

    render(<RemovedOpenerComponent />);

    const opener = screen.getByTestId('temporary-opener');
    await user.click(opener);

    // Modal is open, opener is removed from DOM
    expect(screen.queryByTestId('temporary-opener')).not.toBeInTheDocument();
    expect(screen.getByTestId('close-btn')).toHaveFocus();

    // Closing modal does not throw even though opener is gone
    await user.click(screen.getByTestId('close-btn'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
