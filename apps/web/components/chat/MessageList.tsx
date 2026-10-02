"use client";

import type { Citation } from "@/lib/api-client";

export interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-2 flex flex-col gap-1 border-t border-slate-200 pt-2">
      <span className="text-xs font-medium text-slate-400">Sources</span>
      {citations.map((c, i) => (
        <a
          key={`${c.document_title}-${i}`}
          href={c.url_or_path}
          target="_blank"
          rel="noopener noreferrer"
          className="truncate text-xs text-blue-600 hover:underline"
          title={c.snippet}
        >
          {c.document_title}
        </a>
      ))}
    </div>
  );
}

export function MessageList({
  messages,
  isStreaming,
}: {
  messages: DisplayMessage[];
  isStreaming: boolean;
}) {
  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6">
      {messages.length === 0 && !isStreaming && (
        <p className="m-auto text-sm text-slate-400">
          Ask a question about your company&apos;s documents to get started.
        </p>
      )}
      {messages.map((m) => (
        <div
          key={m.id}
          className={`max-w-2xl rounded-lg px-4 py-3 text-sm ${
            m.role === "user"
              ? "ml-auto bg-slate-900 text-white"
              : "mr-auto bg-white text-slate-900 shadow-sm"
          }`}
        >
          {m.content ? (
            <p className="whitespace-pre-wrap leading-7">{m.content}</p>
          ) : isStreaming ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-600" />
              <span>Thinking through your sources…</span>
            </div>
          ) : null}
          {m.role === "assistant" && <CitationList citations={m.citations} />}
        </div>
      ))}
    </div>
  );
}
