// src/pages/AdminDashboard.jsx
import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@ui/Card";
import { Gauge, History, Target, PlayCircle, PauseCircle, FileText, Package } from "lucide-react";
import { toast } from "react-hot-toast";
import { useNavigate } from "react-router-dom";

const API = import.meta.env.VITE_API_URL || "/api";

async function getJson(path) {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(`${API}${path}`, { headers });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export default function AdminDashboard() {
  const [budget, setBudget] = useState<number | null>(null);
  const [budgetTotal, setBudgetTotal] = useState<number | null>(null);
  const [warn75, setWarn75] = useState(false);
  const [warn90, setWarn90] = useState(false);
  const [warn100, setWarn100] = useState(false);
  const [backlog, setBacklog] = useState<any[]>([]);
  const [purposeInput, setPurposeInput] = useState("");
  const [blueprint, setBlueprint] = useState("");
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [allowResearch, setAllowResearch] = useState<boolean>(false);
  const [updatingResearch, setUpdatingResearch] = useState(false);
  const [paused, setPaused] = useState(false);
  const [purposes, setPurposes] = useState<any[]>([]);
  const [currentPurposeId, setCurrentPurposeId] = useState("");
  const [counts, setCounts] = useState({ planned: 0, running: 0, done: 0 });
  const navigate = useNavigate();
  const [lastCount, setLastCount] = useState(0);
  const [alertMsg, setAlertMsg] = useState<string | null>(null);

  const currentPurpose =
    purposes.find((p) => p.id === currentPurposeId)?.name || "";

  const statusInfo: Record<string, { label: string; color: string; tooltip: string }> = {
    todo: { label: "Todo", color: "bg-yellow-500 text-black", tooltip: "Task is not started yet." },
    doing: { label: "In Progress", color: "bg-blue-500 text-white", tooltip: "Task is currently in progress." },
    done: { label: "Done", color: "bg-green-600 text-white", tooltip: "Task completed successfully." },
    failed: { label: "Failed", color: "bg-red-600 text-white", tooltip: "Task execution failed." },
    blocked: { label: "Blocked", color: "bg-gray-500 text-white", tooltip: "Task was blocked and not executed." },
    skipped: { label: "Skipped", color: "bg-gray-500 text-white", tooltip: "Task was skipped (not executed)." },
    budget_exceeded: { label: "Blocked (Budget)", color: "bg-gray-500 text-white", tooltip: "Task skipped due to insufficient budget." }
  };

  // Fetch list of purposes on mount
  useEffect(() => {
    getJson("/purpose")
      .then((data) => {
        setPurposes(data);
        if (data.length > 0) {
          setCurrentPurposeId(data[0].id);
        }
      })
      .catch(() => {});
  }, []);

  // Polling data for selected purpose
  useEffect(() => {
    if (!currentPurposeId) return;
    const controller = new AbortController();
    const tick = () =>
      Promise.all([
        getJson(`/purpose/${currentPurposeId}/status`),
        getJson(`/backlog?purpose_id=${currentPurposeId}`),
        getJson(`/artifacts?purpose_id=${currentPurposeId}`),
        getJson(`/purpose/${currentPurposeId}/graph`)
      ])
        .then(([statusData, backlogData, artifactsData, graphData]) => {
          setBudget(statusData.budget_left);
          setBudgetTotal(statusData.budget_total);
          setBacklog(backlogData);
          setArtifacts(artifactsData);
          setLastCount(artifactsData.length);
          setPaused(!!statusData.paused);
          const tasks = graphData.tasks || [];
          const plannedCount = tasks.filter((t: any) => t.status === "todo").length;
          const runningCount = tasks.filter((t: any) => t.status === "doing").length;
          const doneCount = tasks.filter((t: any) => t.status === "done").length;
          setCounts({ planned: plannedCount, running: runningCount, done: doneCount });
        })
        .catch(() => {
          toast.error("Failed to load data. Please try again later.");
        });

    tick();
    const id = setInterval(tick, 5000);
    return () => {
      clearInterval(id);
      controller.abort();
    };
  }, [currentPurposeId]);

  // Load research setting
  useEffect(() => {
    fetch(`${API}/settings/research`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}` }
    })
      .then((r) => r.json())
      .then((d) => setAllowResearch(!!d.allow_web_research))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!currentPurposeId) return;
    const interval = setInterval(() => {
      getJson(`/artifacts?purpose_id=${currentPurposeId}`)
        .then((arts) => {
          if (arts.length > lastCount) {
            const latest = arts[0];
            if (latest.repo_path.includes("standup")) {
              setAlertMsg("✅ A new Standup Report is available.");
            } else if (latest.repo_path.includes("planning-adjustment")) {
              setAlertMsg(
                "⚠️ A plan adjustment was made to address project risks."
              );
            } else {
              setAlertMsg("ℹ️ New project report available.");
            }
            setLastCount(arts.length);
          }
        })
        .catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [lastCount, currentPurposeId]);

  useEffect(() => {
    if (budgetTotal != null && budget != null) {
      const remaining = budget;
      const total = budgetTotal;
      const usedRatio = 1 - remaining / total;
      if (!warn100 && remaining <= 0) {
        toast.error("Budget exhausted!");
        setWarn100(true);
        setWarn90(true);
        setWarn75(true);
      } else if (!warn90 && usedRatio >= 0.9) {
        toast("⚠️ 90% of budget used");
        setWarn90(true);
        setWarn75(true);
      } else if (!warn75 && usedRatio >= 0.75) {
        toast("⚠️ 75% of budget used");
        setWarn75(true);
      }
    }
  }, [budget, budgetTotal, warn75, warn90, warn100]);

  useEffect(() => {
    if (!localStorage.getItem("skipOnboarding")) {
      setShowOnboarding(true);
    }
  }, []);

  function handleCloseOnboarding() {
    localStorage.setItem("skipOnboarding", "true");
    setShowOnboarding(false);
  }

  function toggleResearch() {
    if (updatingResearch) return;
    setUpdatingResearch(true);
    const next = !allowResearch;
    fetch(`${API}/settings/research`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("token")}`
      },
      body: JSON.stringify({ allow_web_research: next })
    })
      .then((r) => {
        if (!r.ok) throw new Error("Update failed");
        return r.json();
      })
      .then((d) => {
        setAllowResearch(Boolean(d.allow_web_research));
        toast.success(d.allow_web_research ? "Web Research enabled" : "Web Research disabled");
      })
      .catch(() => toast.error("Failed to update research setting"))
      .finally(() => setUpdatingResearch(false));
  }

  function togglePause() {
    if (!currentPurposeId) return;
    const endpoint = paused
      ? `/purpose/${currentPurposeId}/resume`
      : `/purpose/${currentPurposeId}/pause`;
    fetch(`${API}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        Authorization: `Bearer ${localStorage.getItem("token")}`
      }
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to update pipeline state");
        return res.json();
      })
      .then(() => {
        const newState = !paused;
        setPaused(newState);
        toast.success(newState ? "Purpose paused" : "Purpose resumed");
      })
      .catch(() => toast.error("Failed to update pipeline state"));
  }

  const startPipeline = () => {
    fetch(`${API}/purpose`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        Authorization: `Bearer ${localStorage.getItem("token")}`
      },
      body: JSON.stringify({ purpose: purposeInput })
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Failed to start");
        }
        return data;
      })
      .then((data) => {
        setBlueprint(data.blueprint || "");
        setPurposes([...purposes, { id: data.purpose_id, name: purposeInput }]);
        setCurrentPurposeId(data.purpose_id);
        setPurposeInput("");
        // Refresh backlog and artifacts after seeding new tasks
        getJson(`/backlog?purpose_id=${data.purpose_id}`)
          .then((b) => setBacklog(b))
          .catch(() => {});
        getJson(`/artifacts?purpose_id=${data.purpose_id}`)
          .then((a) => {
            setArtifacts(a);
            setLastCount(a.length);
          })
          .catch(() => {});
      })
      .catch((e) => {
        toast.error(e.message || "Failed to start project.");
      });
  };

  return (
    <div className="bg-gray-900 text-white min-h-screen p-4">
      <h1 className="text-3xl font-bold mb-4">Dashboard</h1>
      <p className="mb-4">Übersicht und Steuerung des Projekts.</p>
      {alertMsg && (
        <div className="bg-yellow-100 border-l-4 border-yellow-500 text-yellow-800 px-4 py-3 mb-4">
          <p className="font-medium">
            {alertMsg}{" "}
            <button
              onClick={() => navigate("/reports")}
              className="underline text-blue-600"
            >
              View details
            </button>
          </p>
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4">
        <Card className="bg-slate-900 text-white">
          <CardContent className="p-6 flex flex-col gap-2 items-start">
            <div className="flex items-center gap-2">
              <Gauge className="text-emerald-400" />
              <div>
                <p className="text-sm">Budget left (USD)</p>
                <p className="text-2xl font-bold">
                  {budget !== null ? budget.toFixed(2) : "…"}{" "}
                  <span className="text-base font-normal">
                    / {budgetTotal?.toFixed(2) ?? "…"} USD
                  </span>
                </p>
              </div>
            </div>
            {budgetTotal != null && budget != null && (
              <div className="w-full bg-slate-800 rounded h-3 mt-1">
                <div
                  className={
                    "h-3 rounded " +
                    (budget / budgetTotal <= 0
                      ? "bg-red-600 animate-pulse"
                      : budget / budgetTotal <= 0.1
                      ? "bg-red-500"
                      : budget / budgetTotal <= 0.25
                      ? "bg-yellow-500"
                      : "bg-emerald-500")
                  }
                  style={{ width: `${(100 * (budgetTotal - budget)) / budgetTotal}%` }}
                />
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="bg-slate-900 text-white">
          <CardContent className="p-4">
            <h2 className="text-lg font-semibold mb-2">Web Research</h2>
            <p className="text-sm text-slate-300 mb-3">
              Allow agents to access the public web (search & fetch) to ground their outputs.
            </p>
            <button
              onClick={toggleResearch}
              disabled={updatingResearch}
              className={`px-3 py-2 rounded flex items-center gap-2 font-medium ${
                allowResearch ? "bg-emerald-600 hover:bg-emerald-700" : "bg-slate-700 hover:bg-slate-600"
              }`}
            >
              {allowResearch ? <PauseCircle className="w-4 h-4" /> : <PlayCircle className="w-4 h-4" />}
              {allowResearch ? "Disable" : "Enable"}
            </button>
          </CardContent>
        </Card>
        <Card className="bg-slate-900 text-white">
          <CardContent className="p-4">
            <h2 className="text-lg font-semibold mb-2">Pipeline Status</h2>
            <p className="text-sm mb-1">
              <span className="font-medium">Current Purpose:</span> {currentPurpose || "—"}
            </p>
            <p className="text-sm mb-3">
              <span className="font-medium">Planned:</span> {counts.planned}{" "}
              <span className="font-medium">Running:</span> {counts.running}{" "}
              <span className="font-medium">Done:</span> {counts.done}
            </p>
            <button
              onClick={togglePause}
              className={`px-3 py-1 rounded ${paused ? "bg-emerald-600" : "bg-red-600"} hover:opacity-90 flex items-center gap-1`}
            >
              {paused ? <PlayCircle className="w-4 h-4" /> : <PauseCircle className="w-4 h-4" />}
              {paused ? "Resume" : "Pause"}
            </button>
          </CardContent>
        </Card>

        <Card className="bg-slate-900 text-white col-span-2 max-h-64 overflow-auto">
          <CardContent className="p-4">
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <History /> Backlog
            </h2>
            <ul className="space-y-1 text-sm">
              {backlog.map((t) => (
                <li key={t.id} className="border-b border-slate-700 py-1 flex items-center justify-between">
                  <div>
                    <span className="text-amber-400 font-mono mr-2">{t.id}</span>
                    {t.description}
                  </div>
                  <span
                    className={`ml-2 px-2 py-0.5 rounded ${statusInfo[t.status]?.color} text-xs font-semibold`}
                    title={statusInfo[t.status]?.tooltip}
                  >
                    {statusInfo[t.status]?.label ?? t.status}
                  </span>
                </li>
              ))}
              {backlog.length === 0 && (
                <li className="italic">Queue is empty 🎉</li>
              )}
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-slate-900 text-white col-span-3">
          <CardContent className="p-4">
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <Target /> Define Purpose
            </h2>
            <form onSubmit={(e) => e.preventDefault()} className="flex items-center gap-2">
              <input
                type="text"
                value={purposeInput}
                onChange={(e) => setPurposeInput(e.target.value)}
                placeholder="Enter project purpose..."
                className="flex-1 p-2 rounded bg-slate-800 text-white border border-slate-700"
              />
              <button
                type="button"
                onClick={startPipeline}
                className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 flex items-center gap-1"
              >
                <PlayCircle className="w-4 h-4" /> Start
              </button>
            </form>
          </CardContent>
        </Card>

        {blueprint && (
          <Card className="bg-slate-900 text-white col-span-3">
            <CardContent className="p-4">
              <h2 className="flex items-center gap-2 text-lg mb-2">
                <FileText /> Architecture Blueprint
              </h2>
              <pre className="text-sm whitespace-pre-wrap">{blueprint}</pre>
            </CardContent>
          </Card>
        )}

        <Card className="bg-slate-900 text-white col-span-3 max-h-64 overflow-auto">
          <CardContent className="p-4">
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <Package /> Artifacts
            </h2>
            <ul className="space-y-1 text-sm">
              {artifacts.map((a) => (
                <li key={a.id} className="border-b border-slate-700 py-1">
                  <span className="text-amber-400 font-mono mr-2">{a.task_id}</span>
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-amber-400 hover:underline"
                  >
                    {a.repo_path.replace(/^[^/]+\//, "")}
                  </a>{" "}
                  <span className="text-slate-400 text-xs">
                    ({a.media_type}, {new Date(a.created_at).toLocaleString()})
                  </span>
                </li>
              ))}
              {artifacts.length === 0 && (
                <li className="italic">No artifacts yet</li>
              )}
            </ul>
          </CardContent>
        </Card>
      </div>
      {backlog.length === 0 && (
        <div className="text-red-400 mt-4">Keine Aufgaben verfügbar.</div>
      )}

      {showOnboarding && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
          onClick={handleCloseOnboarding}
        >
          <div
            className="bg-white text-slate-900 p-6 rounded shadow-lg max-w-lg w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-bold mb-3">Willkommen beim AI-Org Dashboard</h2>
            <p className="mb-4 text-sm">
              Dieses kurze Tutorial hilft Ihnen beim Einstieg. Hier erfahren Sie,
              wie Sie ein neues KI-Projekt anlegen und den Fortschritt überwachen.
            </p>
            <ul className="list-disc list-inside text-sm mb-4 space-y-1">
              <li><b>Projektziel festlegen:</b> Geben Sie im Formular <em>“Define Purpose”</em> ein neues Projektziel ein. Dadurch wird ein initialer Aufgaben-Graph erzeugt.</li>
              <li><b>Task-Graph verstehen:</b> Im <em>Pipeline-Graph</em> werden alle Tasks als Knoten dargestellt (Größe entspricht Business Value, Farbe entspricht Status).</li>
              <li><b>Backlog & Artefakte:</b> Links sehen Sie die <em>Backlog</em>-Liste aller anstehenden Aufgaben und darunter die vom System generierten <em>Artifacts</em> (Dateien).</li>
              <li><b>Budget beobachten:</b> Oben links zeigt der Budget-Balken den verbrauchten Anteil Ihres Budgets. Warnungen informieren Sie, wenn das Budget knapp wird.</li>
            </ul>
            <button
              onClick={handleCloseOnboarding}
              className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700"
            >
              Los geht's!
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
