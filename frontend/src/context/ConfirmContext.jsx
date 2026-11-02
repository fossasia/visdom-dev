/* Copyright 2017-present, The Visdom Authors */
import { createContext, useCallback, useContext, useRef, useState } from 'react';
import ModalPortal from '../components/ModalPortal';
import PasswordInput from '../components/PasswordInput';

const ConfirmContext = createContext(null);

const DEFAULTS = {
  title: 'Are you sure?',
  message: '',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  danger: false,
  input: false,
  inputType: 'text',
  inputLabel: '',
  placeholder: '',
  defaultValue: '',
};

export const ConfirmProvider = ({ children }) => {
  const [state, setState] = useState(null);
  const [inputValue, setInputValue] = useState('');
  const resolverRef = useRef(null);

  const confirm = useCallback((options = {}) => {
    return new Promise((resolve) => {
      if (resolverRef.current) {
        resolverRef.current(false);
      }
      resolverRef.current = resolve;
      const config = { ...DEFAULTS, ...options };
      setInputValue(config.defaultValue);
      setState(config);
    });
  }, []);

  const close = useCallback((result) => {
    if (resolverRef.current) {
      resolverRef.current(result);
      resolverRef.current = null;
    }
    setState(null);
    setInputValue('');
  }, []);

  const handleCancel = useCallback(() => {
    close(state?.input ? null : false);
  }, [close, state]);

  const handleConfirm = useCallback(() => {
    close(state?.input ? inputValue : true);
  }, [close, state, inputValue]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <ModalPortal onClose={handleCancel} aria-labelledby="confirm-modal-title">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleConfirm();
            }}
          >
            <div className="gc-modal-header gc-confirm-header">
              <span id="confirm-modal-title" className={`gc-modal-title ${state.danger ? 'gc-text-danger' : ''}`}>
                {state.title}
              </span>
            </div>

            {state.message && <p className="gc-panel-sub gc-confirm-message">{state.message}</p>}

            {state.input && (
              <div className="gc-field">
                {state.inputLabel && <label className="gc-label">{state.inputLabel}</label>}
                {state.inputType === 'password' ? (
                  <PasswordInput
                    autoFocus
                    className="gc-input"
                    placeholder={state.placeholder}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    autoComplete="off"
                  />
                ) : (
                  <input
                    autoFocus
                    type={state.inputType}
                    className="gc-input"
                    placeholder={state.placeholder}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    autoComplete="off"
                  />
                )}
              </div>
            )}

            <div className="gc-confirm-actions">
              <button type="button" className="gc-btn" onClick={handleCancel}>
                {state.cancelText}
              </button>
              <button
                type="submit"
                autoFocus={!state.input}
                className={`gc-btn ${state.danger ? 'gc-btn-danger' : 'gc-btn-primary'}`}
              >
                {state.confirmText}
              </button>
            </div>
          </form>
        </ModalPortal>
      )}
    </ConfirmContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useConfirm = () => useContext(ConfirmContext);
