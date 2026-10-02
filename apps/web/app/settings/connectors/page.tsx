"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  apiClient,
  type ConnectorProvider,
  type ConnectorStatus,
  type IngestionJob,
} from "@/lib/api-client";

const PROVIDER_LABELS: Record<ConnectorProvider, string> = {
  google_drive: "Google Drive",
  notion: "Notion",
};

export default function ConnectorsSettingsPage() {
  const { isAuthenticated } = useAuth();
  const router = useRouter();

  const [statuses, setStatuses] = useState<ConnectorStatus[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingProvider, setPendingProvider] = useState<ConnectorProvider | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    Promise.all([apiClient.listConnectors(), apiClient.listIngestionJobs()])
      .then(([nextStatuses, nextJobs]) => {
        setStatuses(nextStatuses);
        setJobs(nextJobs);
      })
      .catch(() => setError("Could not load connector status. Check the API and try again."))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    const refreshTimer = window.setTimeout(() => refresh(), 0);
    return () => window.clearTimeout(refreshTimer);
  }, [isAuthenticated, router, refresh]);

  async function handleConnect(provider: ConnectorProvider) {
    setError(null);
    setNotice(null);
    try {
      const { authorize_url } = await apiClient.getConnectorAuthorizeUrl(provider);
      window.location.assign(authorize_url);
    } catch (err) {
      setError(
        err instanceof Error && err.message.includes("not configured")
          ? `${PROVIDER_LABELS[provider]} is not configured on this server. Add its OAuth client ID and secret to the API environment, then restart the API.`
          : `Could not start connecting ${PROVIDER_LABELS[provider]}. Please try again.`,
      );
    }
  }

  async function handleSyncNow(provider: ConnectorProvider) {
    setError(null);
    setNotice(null);
    setPendingProvider(provider);
    try {
      await apiClient.syncConnectorNow(provider);
      setNotice(`${PROVIDER_LABELS[provider]} sync queued. It will run in the background.`);
      refresh();
    } catch {
      setError(`Could not queue a sync for ${PROVIDER_LABELS[provider]}.`);
    } finally {
      setPendingProvider(null);
    }
  }

  if (!isAuthenticated) return null;

  return (
    <main className="mx-auto min-h-screen w-full max-w-4xl px-5 py-8 sm:px-8">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">Workspace settings</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Connected data sources</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
        Connect Google Drive or Notion so the assistant can search and cite your company&apos;s
        own documents. Re-syncs run automatically every few hours once connected.
          </p>
        </div>
        <button type="button" onClick={() => router.push("/chat")} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50">
          Back to chat
        </button>
      </div>

      {error && <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800">{error}</div>}
      {notice && <div className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-800">{notice}</div>}

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {["drive", "notion"].map((item) => <div key={item} className="h-44 animate-pulse rounded-2xl border border-slate-200 bg-white" />)}
        </div>
      ) : <div className="grid gap-4 sm:grid-cols-2">
        {statuses.map((status) => (
          <div
            key={status.provider}
            className="flex min-h-44 flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.05)]"
          >
            <div className="flex items-start justify-between gap-3">
              <div><p className="font-semibold text-slate-950">{PROVIDER_LABELS[status.provider]}</p><p className="mt-1 text-sm text-slate-500">{status.connected ? "Connected and searchable" : status.configured ? "Ready to connect" : "Setup required"}</p></div>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${status.connected ? "bg-emerald-100 text-emerald-700" : status.configured ? "bg-cyan-100 text-cyan-700" : "bg-amber-100 text-amber-800"}`}>{status.connected ? "Live" : status.configured ? "Ready" : "Needs setup"}</span>
            </div>
            {status.connected ? (
              <button
                type="button"
                onClick={() => handleSyncNow(status.provider)}
                disabled={pendingProvider === status.provider}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {pendingProvider === status.provider ? "Queuing…" : "Sync now"}
              </button>
            ) : status.configured ? (
              <button
                type="button"
                onClick={() => handleConnect(status.provider)}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
              >
                Connect
              </button>
            ) : <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">An administrator must configure OAuth credentials in the API environment.</p>}
          </div>
        ))}
      </div>}

      <h2 className="mt-10 text-lg font-semibold text-slate-950">Recent sync jobs</h2>
      <div className="mt-3 divide-y divide-slate-200 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_10px_30px_rgba(15,23,42,0.04)]">
        {jobs.length === 0 && <p className="p-4 text-sm text-slate-400">No sync jobs yet.</p>}
        {jobs.map((job) => (
          <div key={job.id} className="flex items-center justify-between p-3 text-sm">
            <span className="text-slate-700">{PROVIDER_LABELS[job.source as ConnectorProvider] ?? job.source}</span>
            <span className="text-slate-500">
              {job.status}
              {job.status === "succeeded" && ` · ${job.document_count} docs`}
              {job.status === "failed" && job.error_message ? ` · ${job.error_message}` : ""}
            </span>
          </div>
        ))}
      </div>
    </main>
  );
}
