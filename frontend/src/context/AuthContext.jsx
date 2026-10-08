/* Copyright 2017-present, The Visdom Authors */
import { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';
import { clearAppStorage } from '../utils/storage';
import { clearRequestCache } from '../utils/requestCache';

const AuthContext = createContext(null);

const resetClientState = () => {
  clearAppStorage();
  clearRequestCache();
};

// eslint-disable-next-line react-refresh/only-export-components
export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
});

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const requestInterceptor = api.interceptors.request.use(
      (config) => {
        if (accessToken) {
          config.headers['Authorization'] = `Bearer ${accessToken}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    return () => {
      api.interceptors.request.eject(requestInterceptor);
    };
  }, [accessToken]);

  useEffect(() => {
    const responseInterceptor = api.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;
        
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;
          try {
            const refreshResponse = await axios.post('/api/v1/auth/refresh', {}, { withCredentials: true });
            const newAccessToken = refreshResponse.data.access_token;
            
            setAccessToken(newAccessToken);
            
            originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`;
            return api(originalRequest);
          } catch (refreshError) {
            resetClientState();
            setAccessToken(null);
            setUser(null);
            return Promise.reject(refreshError);
          }
        }
        return Promise.reject(error);
      }
    );

    return () => {
      api.interceptors.response.eject(responseInterceptor);
    };
  }, []);

  useEffect(() => {
    const initializeAuth = async () => {
      try {
        const refreshResponse = await axios.post('/api/v1/auth/refresh', {}, { withCredentials: true });
        const initialToken = refreshResponse.data.access_token;
        setAccessToken(initialToken);
        
        const userResponse = await axios.get('/api/v1/auth/me', {
          headers: { Authorization: `Bearer ${initialToken}` }
        });
        setUser(userResponse.data);
      } catch (e) { // eslint-disable-line no-unused-vars
        setUser(null);
        setAccessToken(null);
      } finally {
        setLoading(false);
      }
    };

    initializeAuth();
  }, []);

  const login = async (email, password) => {
    resetClientState();

    const params = new URLSearchParams();
    params.append('username', email);
    params.append('password', password);

    const loginResponse = await axios.post('/api/v1/auth/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      withCredentials: true,
    });

    const token = loginResponse.data.access_token;
    setAccessToken(token);

    const userResponse = await axios.get('/api/v1/auth/me', {
      headers: { Authorization: `Bearer ${token}` }
    });
    setUser(userResponse.data);
    return userResponse.data;
  };

  const register = async (email, password, username) => {
    const response = await axios.post('/api/v1/auth/register', { email, password, username: username || undefined });
    return response.data;
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout');
    } catch (e) {  
      console.error('Logout error', e);
    } finally {
      resetClientState();
      setAccessToken(null);
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{ user, accessToken, loading, login, register, logout, setUser, setAccessToken }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);
