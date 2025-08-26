import React, { useEffect, useState } from "react";
import PurposeInput from "../components/pipeline/PurposeInput";
import StatusIndicator from "../components/pipeline/StatusIndicator";
import FeedbackForm from "../components/pipeline/FeedbackForm";

const API = import.meta.env.VITE_API_URL || "/api";

async function apiGetPRD(purpose: string) {
  const res = await fetch(`${API}/getPRD`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ purpose })
  });
  if (!res.ok) throw new Error("Failed to load");
  return res.json();
}

async function apiPostFeedback(target: string, text: string) {
  const res = await fetch(`${API}/postFeedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, text })
  });
  if (!res.ok) throw new Error("Failed to send feedback");
  return res.json();
}

export default function PipelinePage() {
  const [purpose, setPurpose] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "complete">("idle");
  const [prd, setPrd] = useState("");
  const [blueprint, setBlueprint] = useState("");
  const [feedbackPrd, setFeedbackPrd] = useState("");
  const [feedbackArch, setFeedbackArch] = useState("");
  const [submitted, setSubmitted] = useState({ prd: false, arch: false });

  const start = async () => {
    setStatus("loading");
    try {
      const data = await apiGetPRD(purpose);
      setPrd(data.prdContent ?? "");
      setBlueprint(data.blueprintContent ?? "");
      setSubmitted({ prd: false, arch: false });
      setFeedbackPrd("");
      setFeedbackArch("");
      setStatus("ready");
    } catch {
      setStatus("idle");
    }
  };

  const sendFeedback = async (target: "prd" | "arch") => {
    const text = target === "prd" ? feedbackPrd : feedbackArch;
    setStatus("loading");
    try {
      const data = await apiPostFeedback(target === "prd" ? "PRD" : "Blueprint", text);
      setPrd(data.prdContent ?? prd);
      setBlueprint(data.blueprintContent ?? blueprint);
      setSubmitted((s) => ({ ...s, [target]: true }));
      setStatus("ready");
    } catch {
      setStatus("ready");
    }
  };

  useEffect(() => {
    if (submitted.prd && submitted.arch) {
      setStatus("complete");
    }
  }, [submitted]);

  return (
    <div className="p-8 bg-white text-gray-900 space-y-6">
      <PurposeInput value={purpose} onChange={setPurpose} onStart={start} />

      <StatusIndicator status={status} />

      {prd && blueprint && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white border border-gray-200 rounded-lg shadow-md p-4">
            <h2 className="font-semibold mb-2">Product Requirements Document</h2>
            <pre className="text-sm whitespace-pre-wrap overflow-auto max-h-96">{prd}</pre>
            <FeedbackForm
              value={feedbackPrd}
              onChange={setFeedbackPrd}
              onSubmit={() => sendFeedback("prd")}
            />
          </div>
          <div className="bg-white border border-gray-200 rounded-lg shadow-md p-4">
            <h2 className="font-semibold mb-2">Architektur-Blueprint</h2>
            <pre className="text-sm whitespace-pre-wrap overflow-auto max-h-96">{blueprint}</pre>
            <FeedbackForm
              value={feedbackArch}
              onChange={setFeedbackArch}
              onSubmit={() => sendFeedback("arch")}
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
