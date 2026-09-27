/**
 * The auth token, backed by localStorage, exposed as a React-subscribable
 * external store (useSyncExternalStore) instead of effect+setState — avoids
 * both the hydration mismatch and the "setState in effect" anti-pattern.
 */

const TOKEN_STORAGE_KEY = "knowledge_agent_access_token";
const listeners = new Set<() => void>();

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // localStorage unavailable (private mode, etc.) -- session just won't persist.
  }
  listeners.forEach((listener) => listener());
}

export function subscribeToToken(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function getTokenServerSnapshot(): string | null {
  return null;
}
