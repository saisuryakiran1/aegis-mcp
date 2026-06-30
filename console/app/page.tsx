"use client";

import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type PendingCall = {
  pending_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  risk_score: number;
  explanation: string;
  status: string;
  reviewer: string | null;
  session_id: string;
  created_at: string;
  updated_at: string;
};

function statusBadge(status: string) {
  const base = "inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase";
  if (status === "pending") return `${base} bg-amber-500/20 text-amber-300 border border-amber-500/40`;
  if (status === "approved") return `${base} bg-green-500/20 text-green-300 border border-green-500/40`;
  if (status === "rejected") return `${base} bg-red-500/20 text-red-300 border border-red-500/40`;
  return `${base} bg-red-500/20 text-red-300 border border-red-500/40`;
}

export default function Home() {
  const [calls, setCalls] = useState<PendingCall[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchCalls = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/pending`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setCalls(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCalls();
    const interval = setInterval(fetchCalls, 3000);
    return () => clearInterval(interval);
  }, [fetchCalls]);

  async function handleAction(pendingId: string, action: "approve" | "reject") {
    await fetch(`${API_BASE}/v1/pending/${pendingId}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer: "console-user" }),
    });
    fetchCalls();
  }

  return (
    <main className="max-w-4xl mx-auto p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Aegis-MCP Review Console</h1>
        <p className="text-slate-400 text-sm mt-1">
          Polling {API_BASE}/v1/pending every 3s
        </p>
      </header>

      {loading && <p className="text-slate-400">Loading…</p>}
      {error && (
        <p className="text-red-400 bg-red-950/40 border border-red-800 rounded p-3">
          {error} — is main.py running on port 8000?
        </p>
      )}

      {!loading && calls.length === 0 && !error && (
        <p className="text-slate-500">No pending or recent calls.</p>
      )}

      <div className="space-y-4">
        {calls.map((call) => (
          <article
            key={call.pending_id}
            className="border border-slate-700 rounded-lg p-4 bg-slate-900/60 space-y-3"
          >
            <div className="flex items-center justify-between gap-4">
              <h2 className="font-mono font-semibold text-lg">{call.tool_name}</h2>
              <span className={statusBadge(call.status)}>{call.status}</span>
            </div>

            <div className="text-sm text-slate-400">
              Risk score: <span className="text-slate-200">{call.risk_score}</span>
              {" · "}
              Session: <span className="font-mono">{call.session_id || "—"}</span>
            </div>

            <p className="text-sm">{call.explanation}</p>

            <pre className="text-xs bg-slate-950 border border-slate-800 rounded p-3 overflow-x-auto">
              {JSON.stringify(call.arguments, null, 2)}
            </pre>

            {call.status === "pending" && (
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => handleAction(call.pending_id, "approve")}
                  className="px-4 py-1.5 rounded bg-green-700 hover:bg-green-600 text-sm font-medium"
                >
                  Approve
                </button>
                <button
                  onClick={() => handleAction(call.pending_id, "reject")}
                  className="px-4 py-1.5 rounded bg-red-800 hover:bg-red-700 text-sm font-medium"
                >
                  Reject
                </button>
              </div>
            )}

            {call.reviewer && (
              <p className="text-xs text-slate-500">Reviewer: {call.reviewer}</p>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}
