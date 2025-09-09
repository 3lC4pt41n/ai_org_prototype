// src/pages/AdminDashboard.jsx
import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@ui/Card";
import { Gauge, History, Target, PlayCircle, PauseCircle, Package } from "lucide-react";
import { toast } from "react-hot-toast";
import { useNavigate } from "react-router-dom";
import { getJson, postJson, API_BASE } from "@api";

export default function AdminDashboard() {
  const [budget, setBudget] = useState<number | null>(null);
  const [budgetTotal, setBudgetTotal] = useState<number | null>(null);
  const [warn75, setWarn75] = useState(false);
  const [warn90, setWarn90] = useState(false);
  const [warn100, setWarn100] = useState(false);
  const [backlog, setBacklog] = useState<any[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [allowResearch, setAllowResearch] = useState<boolean>(false);
  const [updatingResearch, setUpdatingResearch] = useState(false);
  const [paused, setPaused] = useState(false);
  const [purposes, setPurposes] = useState<any[]>([]);
  const [currentPurposeId, setCurrentPurposeId] = useState("");
  const [purposeName, setPurposeName] = useState("");
  const [requirements, setRequirements] = useState("");
  const [blueprint, setBlueprint] = useState("");
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

  // Load overall budget on mount
  useEffect(() => {
    getJson("/")
      .then((d) => {
        setBudget(d.budget_left);
        setBudgetTotal(d.budget_total);
      })
      .catch(() => {});
  }, []);

  // Fetch list of purposes on mount
  useEffect(() => {
    getJson("/purposes")
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
        getJson(`/purposes/${currentPurposeId}/status`),
        getJson(`/backlog?purpose_id=${currentPurposeId}`),
        getJson(`/artifacts?purpose_id=${currentPurposeId}`),
        getJson(`/purposes/${currentPurposeId}/graph`)
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
    fetch(`${API_BASE}/settings/research`, {
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
    fetch(`${API_BASE}/settings/research`, {
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
      ? `/purposes/${currentPurposeId}/start`
      : `/purposes/${currentPurposeId}/pause`;
    fetch(`${API_BASE}${endpoint}`, {
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
        toast.success(newState ? "Pipeline pausiert" : "Pipeline fortgesetzt");
      })
      .catch(() => toast.error("Failed to update pipeline state"));
  }

  async function handleCreatePurpose() {
    try {
      const res = await postJson("/purposes", { purpose: purposeName });
      setCurrentPurposeId(res.purpose_id);
      setRequirements(res.requirements);
      setBlueprint(res.blueprint);
      setPurposeName("");
      getJson("/purposes").then(setPurposes).catch(() => {});
      getJson(`/artifacts?purpose_id=${res.purpose_id}`).then(setArtifacts).catch(() => {});
    } catch {
      toast.error("Failed to create purpose");
    }
  }

  function downloadArtifactFile(artifactId: string, filename: string) {
    const token = localStorage.getItem("token");
    fetch(`${API_BASE}/artifact/${artifactId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then((res) => {
        if (!res.ok) throw new Error("Download fehlgeschlagen");
        return res.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(() => toast.error("Download fehlgeschlagen"));
  }

  return (
    <div className="min-h-screen p-4">
      <h1 className="text-3xl font-bold mb-4">Dashboard</h1>
      <p className="mb-4">Übersicht und Steuerung des Projekts.</p>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <select
          value={currentPurposeId}
          onChange={(e) => setCurrentPurposeId(e.target.value)}
          className="border p-2 rounded"
        >
          <option value="">-- Projektziel wählen --</option>
          {purposes.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input
          value={purposeName}
          onChange={(e) => setPurposeName(e.target.value)}
          placeholder="Neues Projektziel"
          className="border p-2 rounded"
        />
        <button
          onClick={handleCreatePurpose}
          className="px-3 py-2 bg-emerald-600 text-white rounded"
        >
          Anlegen
        </button>
      </div>
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
        <Card>
          <CardContent className="p-6 flex flex-col gap-2 items-start">
            <div className="flex items-center gap-2">
              <Gauge className="text-emerald-400" />
              <div>
                <p className="text-sm">Budget left (USD)</p>
                <p className="text-2xl font-bold">
                  {budget?.toFixed(2) ?? "…"}{" "}
                  <span className="text-base font-normal">
                    / {budgetTotal?.toFixed(2) ?? "…"} USD
                  </span>
                </p>
              </div>
            </div>
            {budgetTotal != null && budget != null && (
              <div className="w-full bg-slate-200 rounded h-3 mt-1">
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
        <Card>
          <CardContent className="p-4">
            <h2 className="text-lg font-semibold mb-2">Web Research</h2>
            <p className="text-sm text-slate-600 mb-3">
              Allow agents to access the public web (search & fetch) to ground their outputs.
            </p>
            <button
              onClick={toggleResearch}
              disabled={updatingResearch}
              className={`px-3 py-2 rounded flex items-center gap-2 font-medium ${
                allowResearch ? "bg-emerald-600 hover:bg-emerald-700" : "bg-slate-200 hover:bg-slate-300"
              }`}
            >
              {allowResearch ? <PauseCircle className="w-4 h-4" /> : <PlayCircle className="w-4 h-4" />}
              {allowResearch ? "Disable" : "Enable"}
            </button>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <h2 className="text-lg font-semibold mb-2">Pipeline Status</h2>
            <p className="text-sm mb-1">
              <span className="font-medium">Current Purpose:</span> {currentPurpose || "—"}
            </p>
            <p className="text-sm mb-1">
              <span className="font-medium">Planned:</span> {counts.planned}{" "}
              <span className="font-medium">Running:</span> {counts.running}{" "}
              <span className="font-medium">Done:</span> {counts.done}
            </p>
            <div className="text-sm mb-3 flex items-center gap-2">
              <span className="font-medium">Status:</span>
              <span className={`${paused ? "text-red-600" : "text-green-600"} font-semibold`}>
                {paused ? "Pausiert" : "Läuft"}
              </span>
              <button
                onClick={togglePause}
                className={`px-3 py-1 rounded ${paused ? "bg-emerald-600" : "bg-red-600"} hover:opacity-90 flex items-center gap-1`}
              >
                {paused ? <PlayCircle className="w-5 h-5" /> : <PauseCircle className="w-5 h-5" />}
                {paused ? "Fortsetzen" : "Pausieren"}
              </button>
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-2 max-h-64 overflow-auto">
          <CardContent className="p-4">
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <History /> Backlog
            </h2>
            <ul className="space-y-1 text-sm">
              {backlog.map((t) => (
                <li key={t.id} className="border-b border-slate-200 py-1 flex items-center justify-between">
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

        <Card className="col-span-3">
          <CardContent className="p-4">
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <Target /> Purpose
            </h2>
            <p className="mb-2 text-slate-600">
              Die Purpose-Anlage & Projektsteuerung erfolgt vollständig über die <b>Pipeline</b>.
            </p>
            <a
              href="/pipeline"
              className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 inline-block"
            >
              Zur Pipeline
            </a>
          </CardContent>
        </Card>

        <Card className="col-span-3 max-h-64 overflow-auto">
          <CardContent className="p-4">
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <Package /> Artifacts
            </h2>
            <ul className="space-y-1 text-sm">
              {artifacts.map((a) => (
                <li key={a.id} className="border-b border-slate-200 py-1">
                  <span className="text-amber-400 font-mono mr-2">{a.task_id}</span>
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      downloadArtifactFile(a.id, a.repo_path.split("/").pop() || a.id);
                    }}
                    className="text-amber-400 hover:underline"
                  >
                    {a.repo_path.replace(/^[^/]+\//, "")}
                  </a>{" "}
                  <span className="text-slate-600 text-xs">
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
              <li><b>Projektziel festlegen:</b> Legen Sie das Projektziel in der <em>Pipeline</em>-Ansicht fest. Dadurch wird ein initialer Aufgaben-Graph erzeugt.</li>
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
