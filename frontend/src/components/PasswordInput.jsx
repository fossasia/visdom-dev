/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

const PasswordInput = ({ className = 'visdom-input', ...inputProps }) => {
  const [visible, setVisible] = useState(false);

  return (
    <div className="pw-field">
      <input
        {...inputProps}
        type={visible ? 'text' : 'password'}
        className={`${className} pw-field-input`}
      />
      <button
        type="button"
        className="pw-field-toggle"
        onClick={() => setVisible((prev) => !prev)}
        title={visible ? 'Hide password' : 'Show password'}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
      >
        {visible ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
  );
};

export default PasswordInput;
