import React, { useEffect, useState } from "react";
import PurposeInput from "../components/pipeline/PurposeInput";
import StatusIndicator from "../components/pipeline/StatusIndicator";
import FeedbackForm from "../components/pipeline/FeedbackForm";

const API = import.meta.env.VITE_API_URL || "/api";

interface FeedbackEntry {
  type: string;
  version: number;
  text: string;
  approved: boolean;
}

async function createPurpose(purpose: string) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API}/purpose`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ purpose }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Failed to start");
  }
  return res.json();
}

async function postFeedback(purposeId: string, body: any) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API}/purpose/${purposeId}/feedback`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Failed to send feedback");
  }
  return res.json();
}

async function fetchFeedback(purposeId: string): Promise<FeedbackEntry[]> {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API}/purpose/${purposeId}/feedback`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Failed to load feedback");
  return res.json();
}

async function fetchStatusAndGraph(purposeId: string) {
  const token = localStorage.getItem("token");
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const [statusRes, graphRes] = await Promise.all([
    fetch(`${API}/purpose/${purposeId}/status`, { headers }),
    fetch(`${API}/purpose/${purposeId}/graph`, { headers }),
  ]);
  if (!statusRes.ok || !graphRes.ok) {
    throw new Error("Failed to load status");
  }
  const statusData = await statusRes.json();
  const graphData = await graphRes.json();
  return { statusData, graphData };
}

export default function PipelinePage() {
  const [purpose, setPurpose] = useState("");
  const [purposeId, setPurposeId] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "complete">(
    "idle",
  );
  const [prd, setPrd] = useState("");
  const [blueprint, setBlueprint] = useState("");
  const [feedbackPrd, setFeedbackPrd] = useState("");
  const [feedbackArch, setFeedbackArch] = useState("");
  const [historyPrd, setHistoryPrd] = useState<FeedbackEntry[]>([]);
  const [historyArch, setHistoryArch] = useState<FeedbackEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const [counts, setCounts] = useState({ done: 0, doing: 0, todo: 0 });

  const approvedPrd = historyPrd.some((h) => h.approved);
  const approvedArch = historyArch.some((h) => h.approved);

  const loadHistory = async (pid: string) => {
    try {
      const data = await fetchFeedback(pid);
      setHistoryPrd(data.filter((d) => d.type === "prd"));
      setHistoryArch(data.filter((d) => d.type === "blueprint"));
    } catch {
      // ignore
    }
  };

  const loadStatus = async (pid: string) => {
    try {
      const { statusData, graphData } = await fetchStatusAndGraph(pid);
      setPaused(!!statusData.paused);
      const tasks = graphData.tasks || [];
      setCounts({
        done: tasks.filter((t: any) => t.status === "done").length,
        doing: tasks.filter((t: any) => t.status === "doing").length,
        todo: tasks.filter((t: any) => t.status === "todo").length,
      });
    } catch {
      // ignore
    }
  };

  const start = async () => {
    setStatus("loading");
    try {
      const data = await createPurpose(purpose);
      setPrd(data.requirements ?? "");
      setBlueprint(data.blueprint ?? "");
      setPurposeId(data.purpose_id);
      setFeedbackPrd("");
      setFeedbackArch("");
      setHistoryPrd([]);
      setHistoryArch([]);
      await loadHistory(data.purpose_id);
      await loadStatus(data.purpose_id);
      setStatus("ready");
    } catch {
      setStatus("idle");
    }
  };

  const sendFeedback = async (type: "prd" | "blueprint") => {
    if (!purposeId) return;
    const text = type === "prd" ? feedbackPrd : feedbackArch;
    setStatus("loading");
    try {
      const data = await postFeedback(purposeId, { type, text });
      setPrd(data.prdContent ?? prd);
      setBlueprint(data.blueprintContent ?? blueprint);
      if (type === "prd") setFeedbackPrd("");
      if (type === "blueprint") setFeedbackArch("");
      await loadHistory(purposeId);
      await loadStatus(purposeId);
      setStatus("ready");
    } catch {
      setStatus("ready");
    }
  };

  const approve = async (type: "prd" | "blueprint") => {
    if (!purposeId) return;
    setStatus("loading");
    try {
      await postFeedback(purposeId, { type, approved: true });
      await loadHistory(purposeId);
      await loadStatus(purposeId);
      setStatus("ready");
    } catch {
      setStatus("ready");
    }
  };

  const togglePause = async () => {
    if (!purposeId) return;
    const token = localStorage.getItem("token");
    const endpoint = paused
      ? `/purpose/${purposeId}/resume`
      : `/purpose/${purposeId}/pause`;
    try {
      await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      await loadStatus(purposeId);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (approvedPrd && approvedArch) {
      setStatus("complete");
    }
  }, [approvedPrd, approvedArch]);

  useEffect(() => {
    if (!purposeId) return;
    const id = setInterval(() => loadStatus(purposeId), 5000);
    return () => clearInterval(id);
  }, [purposeId]);

  return (
    <div className="p-8 bg-white text-gray-900 space-y-6">
      <PurposeInput value={purpose} onChange={setPurpose} onStart={start} />

      {purposeId && (
        <div className="flex justify-between items-center text-sm">
          <span className="text-gray-600">
            Purpose ID: <span className="font-mono">{purposeId}</span>
          </span>
          <div className="flex items-center gap-2">
            <div className="flex gap-2">
              <span className="px-2 py-0.5 rounded bg-green-500 text-white text-xs">
                Done {counts.done}
              </span>
              <span className="px-2 py-0.5 rounded bg-blue-500 text-white text-xs">
                Doing {counts.doing}
              </span>
              <span className="px-2 py-0.5 rounded bg-gray-500 text-white text-xs">
                Todo {counts.todo}
              </span>
            </div>
            <button
              className={`px-3 py-1 rounded text-white hover:opacity-90 ${
                paused ? "bg-emerald-600" : "bg-red-600"
              }`}
              onClick={togglePause}
            >
              {paused ? "Fortsetzen" : "Pause"}
            </button>
          </div>
        </div>
      )}

      <StatusIndicator status={status} />

      {prd && blueprint && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white border border-gray-200 rounded-lg shadow-md p-4">
            <h2 className="font-semibold mb-2">Product Requirements Document</h2>
            <pre className="text-sm whitespace-pre-wrap overflow-auto max-h-96">{prd}</pre>
            <FeedbackForm
              value={feedbackPrd}
              onChange={setFeedbackPrd}
              onSend={() => sendFeedback("prd")}
              onApprove={() => approve("prd")}
              history={historyPrd}
              disabled={approvedPrd}
            />
          </div>
          <div className="bg-white border border-gray-200 rounded-lg shadow-md p-4">
            <h2 className="font-semibold mb-2">Architektur-Blueprint</h2>
            <pre className="text-sm whitespace-pre-wrap overflow-auto max-h-96">{blueprint}</pre>
            <FeedbackForm
              value={feedbackArch}
              onChange={setFeedbackArch}
              onSend={() => sendFeedback("blueprint")}
              onApprove={() => approve("blueprint")}
              history={historyArch}
              disabled={approvedArch}
            />
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <button className="btn btn-primary" disabled={status !== "complete"}>
          Weiter
        </button>
      </div>
    </div>
  );
}

