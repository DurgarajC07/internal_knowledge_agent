"use client";

import Link from "next/link";
import type { Conversation } from "@/lib/api-client";

interface SidebarProps {
  conversations: Conversation[];
  selectedConversationId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onLogout: () => void;
}

export function Sidebar({
  conversations,
  selectedConversationId,
  onSelect,
  onNewChat,
  onLogout,
}: SidebarProps) {
  return (
    <aside className="flex h-full w-64 flex-col border-r border-slate-200 bg-white">
      <div className="p-3">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          + New chat
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2">
        {conversations.length === 0 && (
          <p className="px-2 py-4 text-sm text-slate-400">No conversations yet.</p>
        )}
        {conversations.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => onSelect(c.id)}
            className={`mb-1 w-full truncate rounded-md px-3 py-2 text-left text-sm ${
              c.id === selectedConversationId
                ? "bg-slate-100 font-medium text-slate-900"
                : "text-slate-600 hover:bg-slate-50"
            }`}
          >
            {c.title ?? "Untitled conversation"}
          </button>
        ))}
      </nav>

      <div className="border-t border-slate-200 p-3 space-y-2">
        <Link
          href="/settings/connectors"
          className="block text-sm text-slate-500 hover:text-slate-700"
        >
          Connected data sources
        </Link>
        <button
          type="button"
          onClick={onLogout}
          className="w-full text-left text-sm text-slate-500 hover:text-slate-700"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
