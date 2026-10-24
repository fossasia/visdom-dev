/* Copyright 2017-present, The Visdom Authors */
import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../../context/AuthContext';
import { parseApiError } from '../../utils/helpers';
import ModalPortal from '../ModalPortal';

const CheckoutModal = ({ plan, onClose, onComplete }) => {
  const mountRef = useRef(null);
  const completeRef = useRef(onComplete);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    completeRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    let live = true;
    let checkout = null;
    const open = async () => {
      try {
        const { data } = await api.post('/billing/checkout', { tier: plan.id });
        if (!live) return;
        const { loadStripe } = await import('@stripe/stripe-js/pure');
        const stripe = await loadStripe(data.publishable_key);
        if (!live) return;
        if (!stripe) throw new Error('unavailable');
        checkout = await stripe.createEmbeddedCheckoutPage({
          fetchClientSecret: async () => data.client_secret,
          onComplete: () => completeRef.current(data.session_id),
        });
        if (!live) {
          checkout.destroy();
          return;
        }
        checkout.mount(mountRef.current);
        setLoading(false);
      } catch (err) {
        if (!live) return;
        setError(parseApiError(err, 'The payment form could not be opened. Try again shortly.'));
        setLoading(false);
      }
    };
    open();
    return () => {
      live = false;
      checkout?.destroy();
    };
  }, [plan.id]);

  return (
    <ModalPortal onClose={() => {}} wide>
      <div className="gc-modal-header">
        <span className="gc-modal-title">Upgrade to {plan.name}</span>
        <button className="gc-modal-close" onClick={onClose} type="button" aria-label="Close">
          <X size={16} />
        </button>
      </div>
      {error && <div className="gc-form-error">{error}</div>}
      {loading && !error && <div className="gc-empty">Opening the payment form...</div>}
      <div ref={mountRef} className="gc-checkout-frame" />
    </ModalPortal>
  );
};

export default CheckoutModal;
