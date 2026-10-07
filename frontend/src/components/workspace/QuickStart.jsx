/* Copyright 2017-present, The Visdom Authors */
import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { useToast } from '../toast/useToast';
import { copyToClipboard } from '../../utils/clipboard';
import { CLIENT_INSTALL, plotSnippet } from '../../utils/quickstart';

const CodeBlock = ({ label, code, what }) => {
  const toast = useToast();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const ok = await copyToClipboard(code);
    if (!ok) {
      toast.error(`Could not copy the ${what}.`);
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success(`Copied the ${what}.`);
  };

  return (
    <div className="gc-code">
      <div className="gc-code-head">
        <span>{label}</span>
        <button
          type="button"
          className="gc-btn-unstyled-flex"
          onClick={handleCopy}
          title={`Copy the ${what}`}
          aria-label={`Copy the ${what}`}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      <pre className="gc-code-body">{code}</pre>
    </div>
  );
};

const QuickStart = ({ apiKey, workspace, compact = false }) => (
  <div className="gc-quickstart">
    {!compact && (
      <p className="gc-quickstart-lead">
        A key on its own does nothing. These two steps send a plot from your machine,
        and the environment shows up under Open Visualizations.
      </p>
    )}
    <CodeBlock label="1. Install the client" code={CLIENT_INSTALL} what="install command" />
    <CodeBlock label="2. Send a plot" code={plotSnippet({ apiKey, workspace })} what="example" />
    {!apiKey && (
      <p className="gc-quickstart-note">
        Paste your own key in place of the placeholder. Keys are shown once, when you generate them.
      </p>
    )}
  </div>
);

export default QuickStart;
