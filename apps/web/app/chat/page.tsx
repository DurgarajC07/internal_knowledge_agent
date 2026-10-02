"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiClient, type Citation, type Conversation } from "@/lib/api-client";
import { Sidebar } from "@/components/chat/Sidebar";
import { MessageList, type DisplayMessage } from "@/components/chat/MessageList";
import { Composer } from "@/components/chat/Composer";

export default function ChatPage() {
  const { isAuthenticated, logout } = useAuth();
  const router = useRouter();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!isAuthenticated) router.replace("/login");
  }, [isAuthenticated, router]);

  const refreshConversations = useCallback(async () => {
    const list = await apiClient.listConversations();
    setConversations(list);
    return list;
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    apiClient
      .listConversations()
      .then((list) => {
        if (!cancelled) setConversations(list);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load conversations.");
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  async function handleSelectConversation(id: string) {
    setError(null);
    try {
      const detail = await apiClient.getConversation(id);
      setSelectedConversationId(id);
      setMessages(detail.messages.filter((m) => m.role === "user" || m.role === "assistant").map((m) => ({ id: m.id, role: m.role as "user" | "assistant", content: m.content, citations: m.citations })));
    } catch {
      setError("Could not open that conversation. Please try again.");
    }
  }

  function handleNewChat() {
    setSelectedConversationId(null);
    setMessages([]);
    setError(null);
  }

  async function handleSend(message: string) {
    setError(null);
    const userMessage: DisplayMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: message,
      citations: [],
    };
    const assistantId = `local-${Date.now()}-assistant`;
    setMessages((prev) => [...prev, userMessage, { id: assistantId, role: "assistant", content: "", citations: [] }]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    let assistantText = "";
    let citations: Citation[] = [];

    try {
      await apiClient.streamChat(message, selectedConversationId, (event) => {
        if (event.type === "token" && event.data) {
          assistantText += event.data;
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: assistantText } : m)),
          );
        } else if (event.type === "citations" && event.citations) {
          citations = event.citations;
          setMessages((prev) => (prev.map((m) => (m.id === assistantId ? { ...m, citations } : m))));
        } else if (event.type === "done") {
          if (event.conversation_id && event.conversation_id !== selectedConversationId) {
            setSelectedConversationId(event.conversation_id);
          }
          refreshConversations().catch(() => undefined);
        } else if (event.type === "error") {
          setError(event.data ?? "The assistant ran into an error.");
        }
      }, controller.signal);
    } catch {
      setError("Something went wrong while getting a response. Please try again.");
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }

  function handleStop() {
    abortRef.current?.abort();
    setIsStreaming(false);
  }

  if (!isAuthenticated) return null;

  return (
    <div className="flex h-screen w-full">
      <Sidebar
        conversations={conversations}
        selectedConversationId={selectedConversationId}
        onSelect={handleSelectConversation}
        onNewChat={handleNewChat}
        onLogout={() => {
          logout();
          router.replace("/login");
        }}
      />
      <main className="flex flex-1 flex-col">
        {error && (
          <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <MessageList messages={messages} isStreaming={isStreaming} />
        <Composer onSend={handleSend} onStop={handleStop} disabled={isStreaming} />
      </main>
    </div>
  );
}
