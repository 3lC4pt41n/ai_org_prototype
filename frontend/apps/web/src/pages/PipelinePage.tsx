import React, { useEffect, useState } from "react";
import PurposeInput from "../components/pipeline/PurposeInput";
import StatusIndicator from "../components/pipeline/StatusIndicator";
import FeedbackForm from "../components/pipeline/FeedbackForm";
import { getJson, postJson, API_BASE } from "@api-client";
import { toast } from "react-hot-toast";

const API = API_BASE;
const headers = {
  Accept: "application/json",
  Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
};

export default function PipelinePage() {
  const [purpose, setPurpose] = useState("");
  const [purposeId, setPurposeId] = useState<string>();
  const [prd, setPrd] = useState("");
  const [blueprint, setBlueprint] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "complete">("idle");
  const [counts, setCounts] = useState({ todo: 0, doing: 0, done: 0 });
  const [paused, setPaused] = useState(false);
  const [feedbackPrd, setFeedbackPrd] = useState("");
  const [feedbackArch, setFeedbackArch] = useState("");
  const [historyPrd, setHistoryPrd] = useState<any[]>([]);
  const [historyArch, setHistoryArch] = useState<any[]>([]);
  const approvedPrd = historyPrd.some((h) => h.approved);
  const approvedArch = historyArch.some((h) => h.approved);

  // Create a new purpose and start the pipeline
  async function start() {
    setStatus("loading");
    try {
      const data = await createPurpose(purpose);
      setPrd(data.requirements ?? "");
      setBlueprint(data.blueprint ?? "");
      setPurposeId(data.purpose_id);
      setFeedbackPrd("");
      setFeedbackArch("");
      setStatus("ready");
      loadHistory(data.purpose_id);
      loadStatus(data.purpose_id);
    } catch (e: any) {
      toast.error(e.message || "Failed to start pipeline");
      setStatus("idle");
    }
  }

  // Load feedback history
  async function loadHistory(pid: string) {
    const data = await getJson(`/purpose/${pid}/feedback`);
    const prdHistory = data.filter((e: any) => e.type === "prd");
    const archHistory = data.filter((e: any) => e.type === "blueprint");
    setHistoryPrd(prdHistory);
    setHistoryArch(archHistory);
  }

  // Load pipeline status and task counts
  async function loadStatus(pid: string) {
    const [statusRes, graphRes] = await Promise.all([
      fetch(`${API}/purpose/${pid}/status`, { headers }),
      fetch(`${API}/purpose/${pid}/graph`, { headers }),
    ]);
    const statusData = await statusRes.json();
    setPaused(statusData.paused);
    const graphData = await graphRes.json();
    const tasks: any[] = graphData.tasks || [];
    const done = tasks.filter((t) => t.status === "done").length;
    const doing = tasks.filter((t) => t.status === "doing").length;
    const todo = tasks.filter((t) => t.status === "todo").length;
    setCounts({ done, doing, todo });
  }

  // Pause or resume the purpose
  async function togglePause() {
    if (!purposeId) return;
    const endpoint = paused ? `/purpose/${purposeId}/resume` : `/purpose/${purposeId}/pause`;
    await fetch(`${API}${endpoint}`, { method: "POST", headers });
    setPaused(!paused);
  }

  // Send feedback or approval for PRD or architecture
  async function sendFeedback(type: "prd" | "blueprint") {
    if (!purposeId) return;
    const text = type === "prd" ? feedbackPrd : feedbackArch;
    try {
      const data = await postJson(`/purpose/${purposeId}/feedback`, {
        type,
        text,
      });
      if (type === "prd") {
        if (data.prdContent) setPrd(data.prdContent);
        setFeedbackPrd("");
      } else {
        if (data.blueprintContent) setBlueprint(data.blueprintContent);
        setFeedbackArch("");
      }
      loadHistory(purposeId);
      setStatus("ready");
    } catch (e: any) {
      toast.error(e.message || "Failed to send feedback");
    }
  }

  async function approve(type: "prd" | "blueprint") {
    if (!purposeId) return;
    try {
      await postJson(`/purpose/${purposeId}/feedback`, { type, approved: true });
      loadHistory(purposeId);
      if (type === "prd") {
        setStatus(approvedArch ? "complete" : "ready");
      } else {
        setStatus(approvedPrd ? "complete" : "ready");
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to approve");
    }
  }

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
      {!purposeId && (
        <PurposeInput value={purpose} onChange={setPurpose} onStart={start} />
      )}

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

async function createPurpose(purpose: string) {
  const data = await postJson("/purpose", { purpose });
  return data;
}
