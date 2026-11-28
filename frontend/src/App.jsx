/* Copyright 2017-present, The Visdom Authors */
import { useLayoutEffect } from 'react';
import { BrowserRouter, Routes, Route, useLocation, useNavigationType } from 'react-router-dom';
import { ProtectedRoute } from './components/ProtectedRoute';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import LegalPage from './pages/LegalPage';
import { COOKIES, PRIVACY } from './content/legal';
import Dashboard from './pages/Dashboard';
import JoinWorkspace from './pages/JoinWorkspace';
import Start from './pages/Start';
import NotFound from './pages/NotFound';

import SiteLayout from './components/SiteLayout';

function PageNavigation() {
  const { pathname } = useLocation();
  const navigation = useNavigationType();
  useLayoutEffect(() => {
    if (navigation === 'POP') return;
    const heading = document.querySelector('h1') ?? document.querySelector('main');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
    document.documentElement.scrollTop = 0;
  }, [pathname, navigation]);
  return null;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/privacy" element={<LegalPage title="Privacy" sections={PRIVACY} />} />
          <Route path="/cookies" element={<LegalPage title="Cookies" sections={COOKIES} />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route
          path="/"
          element={
            <ProtectedRoute signedOut={<SiteLayout sticky><Start /></SiteLayout>}>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/share/:linkId"
          element={
            <ProtectedRoute>
              <JoinWorkspace />
            </ProtectedRoute>
          }
        />
      </Routes>
      <PageNavigation />
    </BrowserRouter>
  );
}

export default App;
