import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@ui/Card";
import { Gauge, Target, PlayCircle, FileText, Package, ClipboardList } from "lucide-react";
import ReactFlow, { MiniMap, Controls, Background } from "reactflow";
import "reactflow/dist/style.css";
import { getJson, postJson, API_BASE } from "@api";
import { toast } from "react-hot-toast";

const API = API_BASE;

export default function PipelineView() {
  // Pipeline-Status (Pause/Resume, Budget)
  const [pipelinePaused, setPipelinePaused] = useState(false);
  const [budgetLeft, setBudgetLeft] = useState<number | null>(null);
  const [budgetTotal, setBudgetTotal] = useState<number | null>(null);

  // Project (Purpose)
  const [purposeInput, setPurposeInput] = useState("");
  const [purposeId, setPurposeId] = useState<string | null>(null);
  const [purposeName, setPurposeName] = useState<string | null>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [elements, setElements] = useState<any[]>([]);
  const [counts, setCounts] = useState({ done: 0, doing: 0, todo: 0 });
  const [projectPaused, setProjectPaused] = useState(false);

  // Blueprint (Architekturtext)
  const [blueprint, setBlueprint] = useState("");

  // Artifacts
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<any>(null);
  const [artifactContent, setArtifactContent] = useState<string | null>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);

  // Fehlerausgabe
  const [error, setError] = useState<string | null>(null);

  // Hilfsfunktionen zur Berechnung (Status-Farben, Knotengröße)
  function statusColor(status: string) {
    switch (status) {
      case "done":   return "#22c55e";
      case "doing":  return "#fbbf24";
      case "failed": return "#ef4444";
      default:       return "#64748b";
    }
  }
  function getNodeSize(task: any) {
    const base = 40, max = 140;
    const bv = task.business_value ?? 1;
    const scale = Math.log2(bv + 1) * 25 + base;
    return Math.max(base, Math.min(scale, max));
  }

  // On mount: Pipeline-Pause-Status abfragen
  useEffect(() => {
    getJson("/pause")
      .then((d: any) => setPipelinePaused(!!d.paused))
      .catch(() => {});
  }, []);

  // Pipeline-Pause/Resume-Funktionen
  const handlePausePipeline = async () => {
    try {
      await postJson("/pause", {});
      setPipelinePaused(true);
    } catch (e: any) {
      console.error(e);
      toast.error(e.message || "Failed to pause pipeline");
    }
  };
  const handleResumePipeline = async () => {
    try {
      await postJson("/resume", {});
      setPipelinePaused(false);
    } catch (e: any) {
      console.error(e);
      toast.error(e.message || "Failed to resume pipeline");
    }
  };

  // Create new purpose (Projektziel) und starte Pipeline
  const startPipeline = async () => {
    if (!purposeInput) return;
    try {
      const data = await postJson("/purpose", { purpose: purposeInput });
      setPurposeId(data.id);
      setPurposeName(purposeInput);
      setBlueprint(data.blueprint || "");
      setError(null);
      // Budget initial setzen (wird beim Status-Abgleich aktualisiert)
      setBudgetLeft(data.budget_left || null);
      setBudgetTotal(data.budget_total || null);
      // Initialdaten laden
      await loadStatus(data.id);
    } catch (e: any) {
      toast.error(e.message || "Failed to start pipeline");
    }
  };

  // Lade Status, Graph und Artefakte für gegebenen Purpose
  const loadStatus = async (pid: string) => {
    try {
      const [statusData, graphData, artifactsData] = await Promise.all([
        fetch(`${API}/purpose/${pid}/status`).then((r) => r.json()),
        fetch(`${API}/purpose/${pid}/graph`).then((r) => r.json()),
        getJson(`/artifacts?purpose_id=${pid}`),
      ]);
      setProjectPaused(statusData.paused);
      setBudgetLeft(statusData.budget_left);
      setBudgetTotal(statusData.budget_total);

      const tasksList: any[] = graphData.tasks || [];
      setTasks(tasksList);
      // Status-Zählung (Done/Doing/Todo)
      setCounts({
        done: tasksList.filter((t) => t.status === "done").length,
        doing: tasksList.filter((t) => t.status === "doing").length,
        todo: tasksList.filter((t) => t.status === "todo").length,
      });
      // Graph-Elemente (Knoten & Kanten)
      const nodes = tasksList.map((task) => ({
        id: task.id,
        data: {
          label: (
            <div style={{ textAlign: "center" }}>
              <b>{task.description.slice(0, 32)}…</b>
              <div style={{ fontSize: 12, opacity: 0.8, marginTop: 4 }}>
                💸 BV: <b>{task.business_value}</b><br />
                📊 Tokens (Plan/Ist): <b>{task.tokens_plan ?? "-"}</b> / <b>{task.tokens_actual ?? "-"}</b><br />
                <i>Status: {task.status}</i>
              </div>
            </div>
          ),
        },
        position: { x: Math.random() * 600, y: Math.random() * 600 },
        style: {
          border: `3px solid ${statusColor(task.status)}`,
          background: "#1e293b",
          color: "#fff",
          width: getNodeSize(task),
          height: getNodeSize(task),
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 0 8px #0ff5",
          fontSize: 15,
          fontWeight: 500,
        },
      }));
      const edges = (graphData.dependencies || []).map((dep: any) => ({
        id: `${dep.from_id}->${dep.to_id}`,
        source: dep.from_id,
        target: dep.to_id,
      }));
      setElements([...nodes, ...edges]);
      setArtifacts(artifactsData);
    } catch (e: any) {
      console.error(e);
      toast.error(e.message || "Failed to load pipeline data");
      setError(e.message || "Failed to load pipeline data");
    }
  };

  // Polling: alle 5s Status aktualisieren, wenn Purpose gestartet ist
  useEffect(() => {
    if (!purposeId) return;
    const interval = setInterval(() => {
      if (purposeId) loadStatus(purposeId);
    }, 5000);
    return () => clearInterval(interval);
  }, [purposeId]);

  // Pause/Resume für das aktuelle Projekt
  const toggleProjectPause = async () => {
    if (!purposeId) return;
    try {
      if (projectPaused) {
        await postJson(`/purpose/${purposeId}/resume`, {});
        setProjectPaused(false);
      } else {
        await postJson(`/purpose/${purposeId}/pause`, {});
        setProjectPaused(true);
      }
    } catch (e: any) {
      console.error(e);
      toast.error(e.message || "Failed to toggle project pause");
    }
  };

  // Auswahl eines Artefakts: Inhalt laden und Modal öffnen
  const openArtifact = async (artifact: any) => {
    setSelectedArtifact(artifact);
    setArtifactLoading(true);
    try {
      const res = await fetch(`${API}/artifact/${artifact.id}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token") || ""}` },
      });
      const text = await res.text();
      setArtifactContent(text);
    } catch (e: any) {
      console.error(e);
      setArtifactContent(`Failed to load artifact: ${e.message}`);
      toast.error(`Failed to load artifact: ${e.message || ""}`);
    } finally {
      setArtifactLoading(false);
    }
  };
  const closeArtifact = () => {
    setSelectedArtifact(null);
    setArtifactContent(null);
    setArtifactLoading(false);
  };

  return (
    <div className="p-6 bg-gray-50 min-h-screen space-y-6">
      {/* Pipeline-Status und Steuerung */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="max-w-md">
          <div className="flex items-center gap-2">
            <Gauge className="text-emerald-400" />
            <div>
              <p className="text-sm text-gray-600">Verbleibendes Budget (USD)</p>
              <p className="text-2xl font-bold">
                {budgetLeft !== null ? budgetLeft.toFixed(2) : "…"}{" "}
                <span className="text-base font-normal">
                  / {budgetTotal?.toFixed(2) ?? "…"} USD
                </span>
              </p>
            </div>
          </div>
          {budgetLeft != null && budgetTotal != null && (
            <div className="w-full bg-slate-200 rounded h-3 mt-1">
              <div
                className={
                  "h-3 rounded " +
                  (budgetLeft <= 0
                    ? "bg-red-600 animate-pulse"
                    : budgetLeft / budgetTotal <= 0.1
                    ? "bg-red-500"
                    : budgetLeft / budgetTotal <= 0.25
                    ? "bg-yellow-500"
                    : "bg-emerald-500")
                }
                style={{
                  width: `${(100 * (budgetTotal - budgetLeft)) / budgetTotal}%`,
                }}
              />
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handlePausePipeline}
            disabled={pipelinePaused}
            className="px-3 py-1 rounded bg-red-600 text-white disabled:opacity-50"
          >
            Pipeline pausieren
          </button>
          <button
            onClick={handleResumePipeline}
            disabled={!pipelinePaused}
            className="px-3 py-1 rounded bg-emerald-600 text-white disabled:opacity-50"
          >
            Pipeline fortsetzen
          </button>
        </div>
      </div>

      {/* Projektziel / Purpose */}
      <Card>
        <CardContent>
          <h2 className="flex items-center gap-2 text-lg mb-2">
            <Target /> Projektziel (Purpose)
          </h2>
          {!purposeId ? (
            <form
              onSubmit={(e) => { e.preventDefault(); startPipeline(); }}
              className="flex flex-col sm:flex-row items-center gap-2"
            >
              <input
                type="text"
                value={purposeInput}
                onChange={(e) => setPurposeInput(e.target.value)}
                placeholder="Projektziel eingeben..."
                className="flex-1 p-2 border border-gray-300 rounded mb-2 sm:mb-0"
              />
              <button
                type="button"
                onClick={startPipeline}
                className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 flex items-center gap-1"
              >
                <PlayCircle className="w-4 h-4" /> Start
              </button>
            </form>
          ) : (
            <div className="flex flex-col sm:flex-row justify-between items-center text-sm">
              <span className="text-gray-700 mb-2 sm:mb-0">
                Name: <span className="font-semibold">{purposeName}</span> (ID: <span className="font-mono">{purposeId}</span>)
              </span>
              <div className="flex items-center gap-4">
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
                  onClick={toggleProjectPause}
                  className={
                    `px-3 py-1 rounded text-white hover:opacity-90 ` +
                    (projectPaused ? "bg-emerald-600" : "bg-red-600")
                  }
                >
                  {projectPaused ? "Fortsetzen" : "Pausieren"}
                </button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Blueprint-Anzeige */}
      {blueprint && (
        <Card>
          <CardContent>
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <FileText /> Generierter Blueprint
              {/* Optional: Button zum Neuladen könnten wir hier hinzufügen */}
            </h2>
            <pre className="text-sm whitespace-pre-wrap">{blueprint}</pre>
          </CardContent>
        </Card>
      )}

      {/* Backlog */}
      {tasks.length > 0 && (
        <Card>
          <CardContent>
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <ClipboardList /> Backlog
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <h3 className="text-sm font-semibold mb-1">Todo</h3>
                <ul className="space-y-1 text-sm">
                  {tasks.filter((t) => t.status === "todo").map((t) => (
                    <li key={t.id} className="border-b border-slate-200 py-1">
                      {t.description}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-sm font-semibold mb-1">Doing</h3>
                <ul className="space-y-1 text-sm">
                  {tasks.filter((t) => t.status === "doing").map((t) => (
                    <li key={t.id} className="border-b border-slate-200 py-1">
                      {t.description}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-sm font-semibold mb-1">Done</h3>
                <ul className="space-y-1 text-sm">
                  {tasks.filter((t) => t.status === "done").map((t) => (
                    <li key={t.id} className="border-b border-slate-200 py-1">
                      {t.description}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Task-Graph (ReactFlow) */}
      {elements.length > 0 ? (
        <div className="w-full h-[700px] bg-gray-100 rounded-xl shadow-lg">
          <ReactFlow elements={elements} fitView>
            <MiniMap
              nodeStrokeColor={(n) => (n.style?.border as string) ?? "#94a3b8"}
              nodeColor={(n) => (n.style?.background as string) ?? "#cbd5e1"}
            />
            <Controls />
            <Background color="#cbd5e1" gap={18} />
          </ReactFlow>
        </div>
      ) : (
        purposeId && <p className="text-center pt-4 text-gray-600">Keine Aufgaben zum Anzeigen</p>
      )}

      {/* Artifacts-Liste */}
      {artifacts.length > 0 && (
        <Card className="overflow-auto">
          <CardContent>
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <Package /> Artefakte
            </h2>
            <ul className="space-y-1 text-sm">
              {artifacts.map((a) => (
                <li
                  key={a.id}
                  className="border-b border-slate-200 py-1 flex justify-between items-center"
                >
                  <div>
                    <span className="text-amber-400 font-mono mr-2">{a.task_id}</span>
                    {a.repo_path}{" "}
                    <span className="text-slate-600 text-xs">
                      ({a.media_type}, {new Date(a.created_at).toLocaleString()})
                    </span>
                  </div>
                  <button
                    onClick={() => openArtifact(a)}
                    className="text-indigo-600 hover:underline text-xs"
                  >
                    Details
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Modal für Artefakt-Details */}
      {selectedArtifact && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
          onClick={closeArtifact}
        >
          <div
            className="bg-white text-gray-900 p-6 rounded-lg max-w-lg w-full mx-4 overflow-auto max-h-[80vh]"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-semibold mb-2">{selectedArtifact.repo_path}</h3>
            <p className="text-sm mb-4 italic">
              (Dateityp: {selectedArtifact.media_type})
            </p>
            {artifactLoading ? (
              <p className="text-gray-600">Lade Artefaktinhalt...</p>
            ) : (
              <pre className="whitespace-pre-wrap text-sm">
                {artifactContent}
              </pre>
            )}
            <button
              onClick={closeArtifact}
              className="mt-4 px-4 py-2 bg-slate-200 hover:bg-slate-300 rounded"
            >
              Schließen
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
