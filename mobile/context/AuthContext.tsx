/**
 * context/AuthContext.tsx
 * -----------------------
 * PURPOSE:
 *   Global authentication state shared across every screen.
 *   Any screen can call useAuth() to read the current user or call login/logout.
 *
 * CONCEPT — React Context API
 *   Context solves "prop drilling" — passing a value down through many
 *   component layers just so a deep child can use it.
 *
 *   Instead:
 *     1. Create a Context object with createContext()
 *     2. Wrap the app in <AuthProvider> — it holds the state
 *     3. Any child calls useAuth() — React finds the nearest Provider above it
 *
 *   This is the standard pattern for auth state in React/React Native apps.
 *   For more complex state (many slices), you'd use Redux or Zustand instead.
 *
 * CONCEPT — AsyncStorage
 *   React Native has no localStorage/sessionStorage (those are browser APIs).
 *   AsyncStorage is the equivalent: a simple key-value store that persists
 *   across app restarts. It is async (returns Promises) because the native
 *   storage layer is accessed via a bridge.
 *
 *   We store the JWT token here so the user stays logged in after closing the app.
 *
 * EXPORTS:
 *   AuthProvider  — wrap the app root with this
 *   useAuth()     — hook: returns { user, token, login, logout, isLoading }
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import { authApi, saveToken, clearToken, getToken, UserResponse } from '../services/api';

// ── Types ────────────────────────────────────────────────────────────────────
interface AuthState {
  user:      UserResponse | null;
  token:     string | null;
  isLoading: boolean;    // true while checking stored token on startup
  login:     (email: string, password: string) => Promise<void>;
  logout:    () => Promise<void>;
}

// ── Context ──────────────────────────────────────────────────────────────────
const AuthContext = createContext<AuthState | null>(null);

// ── Provider ─────────────────────────────────────────────────────────────────
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,      setUser]      = useState<UserResponse | null>(null);
  const [token,     setToken]     = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount: check if a token is already stored (app restart / re-open).
  useEffect(() => {
    (async () => {
      try {
        const stored = await getToken();
        if (stored) {
          setToken(stored);
          // Verify token is still valid by fetching the current user profile.
          const res = await authApi.me();
          setUser(res.data);
        }
      } catch {
        // Token is expired or invalid — clear it so user lands on Login.
        await clearToken();
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const login = async (email: string, password: string) => {
    const res = await authApi.login({ email, password });
    const jwt = res.data.access_token;

    await saveToken(jwt);
    setToken(jwt);

    // Fetch full user profile now that we have a valid token.
    const profile = await authApi.me();
    setUser(profile.data);
  };

  const logout = async () => {
    await clearToken();
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ─────────────────────────────────────────────────────────────────────
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
