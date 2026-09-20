"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, clearToken, getToken, setCreditsListener, setToken } from "./api";
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
      setUser(await api.me());
    } catch {
      clearToken();
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
