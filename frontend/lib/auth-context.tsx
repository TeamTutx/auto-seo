"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, clearToken, getToken, setCreditsListener, setToken } from "./api";
import type { User } from "./types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/** `api.me()`, retried while the API is unreachable rather than wrong. A 401 is
 *  an answer and is thrown straight away; a network error or 5xx gets up to
 *  about a minute - how long a restarting or waking API takes to come back. */
async function fetchMe(): Promise<User> {
  const deadline = Date.now() + 60_000;
  for (;;) {
    try {
      return await api.me();
    } catch (err) {
      const answered = err instanceof ApiError && err.status < 500;
      if (answered || Date.now() > deadline) throw err;
      await new Promise((resolve) => setTimeout(resolve, 3_000));
    }
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  async function refreshUser() {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await fetchMe());
    } catch (err) {
      // Only a 401 means the token is bad. Anything else - offline, the API
      // restarting, Render waking it - says nothing about the token, and used
      // to delete it anyway: a sleeping API signed everyone out.
      if (err instanceof ApiError && err.status === 401) clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshUser();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Any call that spends a credit refetches the balance, so the sidebar is
  // right without a reload wherever in the app the spending happened.
  useEffect(() => {
    setCreditsListener(() => {
      if (getToken()) api.me().then(setUser).catch(() => {});
    });
    return () => setCreditsListener(null);
  }, []);

  async function login(email: string, password: string) {
    const { access_token } = await api.login(email, password);
    setToken(access_token);
    await refreshUser();
  }

  async function register(email: string, password: string) {
    await api.register(email, password);
    await login(email, password);
  }

  function logout() {
    clearToken();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh: refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
