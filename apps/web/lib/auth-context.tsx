"use client";

import { createContext, useCallback, useContext, useSyncExternalStore } from "react";
import { apiClient } from "./api-client";
import { getStoredToken, getTokenServerSnapshot, setStoredToken, subscribeToToken } from "./token-store";

interface AuthContextValue {
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (tenantName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const token = useSyncExternalStore(subscribeToToken, getStoredToken, getTokenServerSnapshot);
  const isAuthenticated = Boolean(token);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await apiClient.login(email, password);
    setStoredToken(access_token);
  }, []);

  const register = useCallback(async (tenantName: string, email: string, password: string) => {
    const { access_token } = await apiClient.register(tenantName, email, password);
    setStoredToken(access_token);
  }, []);

  const logout = useCallback(() => {
    setStoredToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
