/**
 * The single typed client every component calls through — no ad hoc fetch()
 * calls scattered through components (Rule.md SS10). Types here mirror the
 * backend's Pydantic schemas in packages/core/schemas/*; keep them in sync by
 * hand until a codegen step is added (documented tradeoff, not automated yet).
 */

import { getStoredToken } from "./token-store";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Role = "admin" | "member";

export interface Citation {
  document_title: string;
  url_or_path: string;
  source: string;
  chunk_index: number | null;
  snippet: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface Conversation {
  id: string;
  tenant_id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface ChatStreamEvent {
  type: "token" | "citations" | "error" | "done";
  data?: string | null;
  citations?: Citation[] | null;
  conversation_id?: string | null;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export { getStoredToken, setStoredToken } from "./token-store";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return (await response.json()) as T;
}

export const apiClient = {
  async register(tenantName: string, email: string, password: string): Promise<{ access_token: string }> {
    return request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ tenant_name: tenantName, email, password }),
    });
  },

  async login(email: string, password: string): Promise<{ access_token: string }> {
    return request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async listConversations(): Promise<Conversation[]> {
    return request("/api/conversations");
  },

  async createConversation(title?: string): Promise<Conversation> {
    return request("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title: title ?? null }),
    });
  },

  async getConversation(id: string): Promise<ConversationDetail> {
    return request(`/api/conversations/${id}`);
  },

  /**
   * Streams a chat turn over SSE. Calls `onEvent` for every frame the server
   * sends (token / citations / done / error) as it arrives.
   */
  async streamChat(
    message: string,
    conversationId: string | null,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const token = getStoredToken();
    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message, conversation_id: conversationId }),
      signal,
    });

    if (!response.ok || !response.body) {
      throw new ApiError(response.status, `Chat request failed: ${response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // Normalize CRLF (sse-starlette's default) to LF before splitting on
      // the blank-line frame separator.
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
        if (!dataLine) continue;
        const jsonText = dataLine.slice("data:".length).trim();
        if (!jsonText) continue;
        onEvent(JSON.parse(jsonText) as ChatStreamEvent);
      }
    }
  },
};
