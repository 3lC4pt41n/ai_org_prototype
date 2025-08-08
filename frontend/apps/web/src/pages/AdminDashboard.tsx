// src/pages/AdminDashboard.jsx
import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@ui/Card";
import { Gauge, History, Target, PlayCircle, FileText, Package } from "lucide-react";
import { toast } from "react-hot-toast";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

  const statusInfo: Record<string, { label: string; color: string; tooltip: string }> = {
    todo: { label: "Todo", color: "bg-yellow-500 text-black", tooltip: "Task is not started yet." },
    doing: { label: "In Progress", color: "bg-blue-500 text-white", tooltip: "Task is currently in progress." },
    done: { label: "Done", color: "bg-green-600 text-white", tooltip: "Task completed successfully." },
    failed: { label: "Failed", color: "bg-red-600 text-white", tooltip: "Task execution failed." },
    blocked: { label: "Blocked", color: "bg-gray-500 text-white", tooltip: "Task was blocked and not executed." },
    skipped: { label: "Skipped", color: "bg-gray-500 text-white", tooltip: "Task was skipped (not executed)." },
    budget_exceeded: { label: "Blocked (Budget)", color: "bg-gray-500 text-white", tooltip: "Task skipped due to insufficient budget." }
  };

  useEffect(() => {
    const controller = new AbortController();

    const tick = () =>
      Promise.all([getJson("/"), getJson("/backlog"), getJson("/api/artifacts")])
        .then(([statusData, backlogData, artifactsData]) => {
          setBudget(statusData.budget_left);
          setBudgetTotal(statusData.budget_total);
          setBacklog(backlogData);
          setArtifacts(artifactsData);
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
  }, []);

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetch(`${API}/api/purpose`, {
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
        setPurposeInput("");
        // Refresh backlog and artifacts after seeding new tasks
        getJson("/backlog")
          .then((b) => setBacklog(b))
          .catch(() => {});
        getJson("/api/artifacts")
          .then((a) => setArtifacts(a))
          .catch(() => {});
      })
      .catch((e) => {
        toast.error(e.message || "Failed to start project.");
      });
  };

  return (
    <>
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
            <form onSubmit={handleSubmit} className="flex items-center gap-2">
              <input
                type="text"
                value={purposeInput}
                onChange={(e) => setPurposeInput(e.target.value)}
                placeholder="Enter project purpose..."
                className="flex-1 p-2 rounded bg-slate-800 text-white border border-slate-700"
              />
              <button
                type="submit"
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
    </>
  );
}
