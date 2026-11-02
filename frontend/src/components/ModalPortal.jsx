/* Copyright 2017-present, The Visdom Authors */
import { createContext, useContext, useEffect, useId, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';

const ModalContext = createContext(null);

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'button:not([disabled])',
  'iframe',
  'object',
  'embed',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable]:not([contenteditable="false"])',
].join(', ');

const isElementVisibleAndEnabled = (el, container) => {
  if (!el || el.nodeType !== 1) return false;
  if (el.getAttribute('tabindex') === '-1') return false;
  if (el.disabled || Boolean(el.matches?.(':disabled'))) return false;
  if (el.closest('[hidden]')) return false;
  if (el.closest('[aria-hidden="true"]')) return false;
  if (el.closest('[inert]') || el.inert) return false;

  if (typeof window !== 'undefined' && typeof window.getComputedStyle === 'function') {
    const style = window.getComputedStyle(el);
    if (style.display === 'none') return false;
    if (style.visibility === 'hidden' || style.visibility === 'collapse') return false;

    let parent = el.parentElement;
    while (parent && parent !== document.documentElement) {
      const parentStyle = window.getComputedStyle(parent);
      if (parentStyle.display === 'none') return false;
      if (parent === container) break;
      parent = parent.parentElement;
    }
  }

  return true;
};

const getFocusableElements = (container) => {
  if (!container) return [];
  const elements = Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR));
  return elements.filter((el) => isElementVisibleAndEnabled(el, container));
};

const hasAutoFocus = (el) => {
  return Boolean(
    el &&
    (el.hasAttribute('autofocus') || el.autofocus === true)
  );
};


const focusInsideContainer = (container) => {
  if (!container) return;
  const focusables = getFocusableElements(container);
  const autoFocusEl = focusables.find(hasAutoFocus) || container.querySelector('[autofocus]');

  if (autoFocusEl && focusables.includes(autoFocusEl)) {
    autoFocusEl.focus();
  } else if (focusables.length > 0) {
    focusables[0].focus();
  } else {
    container.focus();
  }
};

// Stack to track open modals for nested modals
const modalStack = [];

const getTopModal = () => {
  if (modalStack.length === 0) return null;
  let top = modalStack[0];
  for (let i = 1; i < modalStack.length; i++) {
    const entry = modalStack[i];
    if (entry.depth > top.depth) {
      top = entry;
    } else if (entry.depth === top.depth) {
      top = entry;
    }
  }
  return top;
};

const ModalPortal = ({
  onClose,
  wide,
  children,
  role = 'dialog',
  'aria-modal': ariaModal = 'true',
  'aria-labelledby': ariaLabelledByProp,
  'aria-label': ariaLabelProp,
  'aria-describedby': ariaDescribedByProp,
  ariaLabelledBy,
  ariaLabel,
  ariaDescribedBy,
  titleId,
  closeOnEscape = true,
  className = '',
  ...rest
}) => {
  const parentModal = useContext(ModalContext);
  const depth = parentModal ? (parentModal.depth || 0) + 1 : 0;

  const dialogRef = useRef(null);
 
  const onCloseRef = useRef(onClose);
  const closeOnEscapeRef = useRef(closeOnEscape);
  const generatedId = useId();

const modalEntry = useMemo(
  () => ({
    depth,
    parent: parentModal,
    get dialog() {
      return dialogRef.current;
    },
  }),
  [depth, parentModal]
);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    closeOnEscapeRef.current = closeOnEscape;
  }, [closeOnEscape]);

  const resolvedLabelledBy = ariaLabelledByProp || ariaLabelledBy || titleId;
  const resolvedLabel = ariaLabelProp || ariaLabel;
  const resolvedDescribedBy = ariaDescribedByProp || ariaDescribedBy;

  // Track the element that was focused before this modal opened
  const previousActiveElementRef = useRef(
    typeof document !== 'undefined' ? document.activeElement : null
  );

  // Fallback: auto-detect visible title if no explicit aria-labelledby or aria-label was passed
  useEffect(() => {
    if (!resolvedLabelledBy && !resolvedLabel && dialogRef.current) {
      const titleEl = dialogRef.current.querySelector('.gc-modal-title');
      if (titleEl) {
        if (!titleEl.id) {
          titleEl.id = generatedId;
        }
        dialogRef.current.setAttribute('aria-labelledby', titleEl.id);
      }
    }
  }, [resolvedLabelledBy, resolvedLabel, generatedId]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    // Capture previous active element if not already captured outside dialog
    if (
      !previousActiveElementRef.current ||
      previousActiveElementRef.current === document.body
    ) {
      if (
        document.activeElement &&
        document.activeElement !== document.body &&
        !dialog.contains(document.activeElement)
      ) {
        previousActiveElementRef.current = document.activeElement;
      }
    }

    // Register this modal in the modal stack
  modalStack.push(modalEntry);

    // Initial focus:
    // 1. If activeElement is already inside dialog and valid, keep it
    // 2. If an autofocus element exists among focusables, focus it
    // 3. Otherwise focus the first focusable element
    // 4. If no focusable elements exist, focus the dialog container itself
    const initialFocusables = getFocusableElements(dialog);
    const autoFocusEl = initialFocusables.find(hasAutoFocus) || dialog.querySelector('[autofocus]');

    if (
      document.activeElement &&
      dialog.contains(document.activeElement) &&
      document.activeElement !== dialog &&
      initialFocusables.includes(document.activeElement)
    ) {
      // Focus is already on a valid focusable inside dialog
    } else if (autoFocusEl && initialFocusables.includes(autoFocusEl)) {
      autoFocusEl.focus();
    } else if (initialFocusables.length > 0) {
      initialFocusables[0].focus();
    } else {
      dialog.focus();
    }

    const handleKeyDown = (e) => {
      // Only the top-most modal handles keyboard events
      const topEntry = getTopModal();
      if (topEntry !== modalEntry) {
        return;
      }

      if (e.key === 'Escape') {
        if (closeOnEscapeRef.current && typeof onCloseRef.current === 'function') {
          e.preventDefault();
          e.stopPropagation();
          onCloseRef.current(e);
        }
        return;
      }

      if (e.key === 'Tab') {
        const currentFocusables = getFocusableElements(dialog);

        if (currentFocusables.length === 0) {
          e.preventDefault();
          dialog.focus();
          return;
        }

        if (currentFocusables.length === 1) {
          e.preventDefault();
          currentFocusables[0].focus();
          return;
        }

        const currentIndex = currentFocusables.indexOf(document.activeElement);
        e.preventDefault();

        if (e.shiftKey) {
          // Shift + Tab (backwards)
          if (currentIndex <= 0) {
            currentFocusables[currentFocusables.length - 1].focus();
          } else {
            currentFocusables[currentIndex - 1].focus();
          }
        } else {
          // Tab (forwards)
          if (currentIndex === -1 || currentIndex >= currentFocusables.length - 1) {
            currentFocusables[0].focus();
          } else {
            currentFocusables[currentIndex + 1].focus();
          }
        }
      }
    };

    // If focus moves outside the active dialog programmatically, pull it back
    const handleFocusIn = (e) => {
  const topEntry = getTopModal();

  if (topEntry !== modalEntry) {
    return;
  }

  // Allow focus inside a nested dialog, even before it is
  // registered in the modal stack.
  const targetDialog = e.target?.closest?.('[role="dialog"]');

  if (targetDialog && targetDialog !== dialog) {
    return;
  }

  if (e.target && !dialog.contains(e.target)) {
    e.preventDefault();
    focusInsideContainer(dialog);
  }
};

    window.addEventListener('keydown', handleKeyDown);
    document.addEventListener('focusin', handleFocusIn);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('focusin', handleFocusIn);

      // Remove from stack
      const index = modalStack.indexOf(modalEntry);
      if (index !== -1) {
        modalStack.splice(index, 1);
      }

      // Restore focus
      const elToFocus = previousActiveElementRef.current;
      const remainingTopModal = getTopModal();

      if (elToFocus && typeof elToFocus.focus === 'function' && document.contains(elToFocus)) {
        // If another modal is still open below this one, only restore focus to elToFocus
        // if elToFocus is inside that remaining modal; otherwise focus inside the remaining modal.
        if (remainingTopModal?.dialog) {
          if (remainingTopModal.dialog.contains(elToFocus)) {
            elToFocus.focus();
            return;
          }
          focusInsideContainer(remainingTopModal.dialog);
          return;
        }

        elToFocus.focus();
        return;
      }

      // If opener element was removed or unavailable, ensure focus stays in remaining modal
      if (remainingTopModal?.dialog) {
        focusInsideContainer(remainingTopModal.dialog);
      }
    };
  }, [modalEntry]);

  const handleOverlayClick = (e) => {
    if (e.target !== e.currentTarget) return;

    // Only topmost modal responds to overlay click
    const topEntry = getTopModal();
    if (topEntry !== modalEntry) return;

    if (typeof onCloseRef.current === 'function') {
      onCloseRef.current(e);
    }
  };

  return createPortal(
    <ModalContext.Provider value={modalEntry}>
      <div className="gc-modal-overlay" onClick={handleOverlayClick}>
        <div
          ref={dialogRef}
          role={role}
          aria-modal={ariaModal}
          aria-labelledby={resolvedLabelledBy || undefined}
          aria-label={resolvedLabel || undefined}
          aria-describedby={resolvedDescribedBy || undefined}
          tabIndex={-1}
          className={`gc-panel gc-modal ${wide ? 'gc-modal-wide' : ''} ${className}`.trim()}
          onClick={(e) => e.stopPropagation()}
          {...rest}
        >
          {children}
        </div>
      </div>
    </ModalContext.Provider>,
    document.body
  );
};

export default ModalPortal;
