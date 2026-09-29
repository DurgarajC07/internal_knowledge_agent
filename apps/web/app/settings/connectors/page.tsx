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

  const refresh = useCallback(() => {
    Promise.all([apiClient.listConnectors(), apiClient.listIngestionJobs()])
      .then(([nextStatuses, nextJobs]) => {
        setStatuses(nextStatuses);
        setJobs(nextJobs);
      })
      .catch(() => setError("Could not load connector status."));
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    refresh();
  }, [isAuthenticated, router, refresh]);

  async function handleConnect(provider: ConnectorProvider) {
    setError(null);
    try {
      const { authorize_url } = await apiClient.getConnectorAuthorizeUrl(provider);
      window.location.assign(authorize_url);
    } catch {
      setError(`Could not start connecting ${PROVIDER_LABELS[provider]}.`);
    }
  }

  async function handleSyncNow(provider: ConnectorProvider) {
    setError(null);
    setPendingProvider(provider);
    try {
      await apiClient.syncConnectorNow(provider);
      refresh();
    } catch {
      setError(`Could not queue a sync for ${PROVIDER_LABELS[provider]}.`);
    } finally {
      setPendingProvider(null);
    }
  }

  if (!isAuthenticated) return null;

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-semibold text-slate-900">Connected data sources</h1>
      <p className="mt-1 text-sm text-slate-500">
        Connect Google Drive or Notion so the assistant can search and cite your company&apos;s
        own documents. Re-syncs run automatically every few hours once connected.
      </p>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <div className="mt-6 space-y-4">
        {statuses.map((status) => (
          <div
            key={status.provider}
            className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-4"
          >
            <div>
              <p className="font-medium text-slate-900">{PROVIDER_LABELS[status.provider]}</p>
              <p className="text-sm text-slate-500">
                {status.connected ? "Connected" : "Not connected"}
              </p>
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
            ) : (
              <button
                type="button"
                onClick={() => handleConnect(status.provider)}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
              >
                Connect
              </button>
            )}
          </div>
        ))}
      </div>

      <h2 className="mt-8 text-sm font-medium text-slate-700">Recent sync jobs</h2>
      <div className="mt-2 divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
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
