/* Copyright 2017-present, The Visdom Authors */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AuthProvider } from './context/AuthContext';
import { ConfirmProvider } from './context/ConfirmContext';
import ToastContainer from './components/toast/ToastContainer';
import './css/index.css';
import './css/workspaces.css';
import './css/toast.css';
import './css/start.css';
import App from './App.jsx';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <ConfirmProvider>
        <App />
        <ToastContainer />
      </ConfirmProvider>
    </AuthProvider>
  </StrictMode>
);
