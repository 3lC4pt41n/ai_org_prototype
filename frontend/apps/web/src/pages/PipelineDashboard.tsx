import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@ui/Card";
import { FileText, Package, PlayCircle, Target } from "lucide-react";
import ReactFlow, { MiniMap, Controls, Background } from "reactflow";
import "reactflow/dist/style.css";

const API = import.meta.env.VITE_API_URL || "/api";
async function getJson(path: string) {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function statusColor(status: string) {
  switch (status) {
    case "done": return "#22c55e";
    case "doing": return "#fbbf24";
    case "failed": return "#ef4444";
    default: return "#64748b";
  }
}

function getNodeSize(task: any) {
  const base = 40;
  const max = 140;
  const bv = task.business_value ?? 1;
  const scale = Math.log2(bv + 1) * 25 + base;
  return Math.max(base, Math.min(scale, max));
}

export default function PipelineDashboard() {
  const [purposeInput, setPurposeInput] = useState("");
  const [blueprint, setBlueprint] = useState("");
  const [elements, setElements] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<any>(null);

  // Periodically refresh graph and artifacts
  useEffect(() => {
    const interval = setInterval(() => {
      refreshData().catch((e) => setError(e.message));
    }, 5000);
    // initial load
    refreshData().catch((e) => setError(e.message));
    return () => clearInterval(interval);
  }, []);

  const refreshData = () => {
    return Promise.all([getJson("/graph"), getJson("/artifacts")]).then(
      ([graphData, artifactsData]) => {
        const nodes = graphData.tasks.map((task: any) => ({
          id: task.id,
          data: {
            label: (
              <div style={{ textAlign: "center" }}>
                <b>{task.description.slice(0, 32)}…</b>
                <div style={{ fontSize: 12, opacity: 0.8, marginTop: 4 }}>
                  💸 BV: <b>{task.business_value}</b>
                  <br />
                  📊 Token Plan/Ist: <b>{task.tokens_plan ?? "-"}</b> / <b>{task.tokens_actual ?? "-"}</b>
                  <br />
                  <i>Status: {task.status}</i>
                </div>
              </div>
            )
          },
          position: { x: Math.random() * 600, y: Math.random() * 600 },
          style: {
            border: `3px solid ${statusColor(task.status)}`,
            background: "#f8fafc",
            color: "#1e293b",
            width: getNodeSize(task),
            height: getNodeSize(task),
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 0 8px #0ff5",
            fontSize: 15,
            fontWeight: 500
          }
        }));
        const edges = graphData.dependencies.map((dep: any) => ({
          id: `${dep.from_id}->${dep.to_id}`,
          source: dep.from_id,
          target: dep.to_id
        }));
        setElements([...nodes, ...edges]);
        setTasks(graphData.tasks);
        setArtifacts(artifactsData);
        setError(null);
      }
    );
  };

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
        setError(null);
        // Refresh graph data after seeding
        refreshData();
      })
      .catch((e) => setError(e.message));
  };

  const handleNodeClick = (_: React.MouseEvent, node: any) => {
    const task = tasks.find((t) => t.id === node.id);
    if (task) {
      setSelectedTask(task);
    }
  };

  const closeModal = () => setSelectedTask(null);

  return (
    <div className="min-h-screen p-4 space-y-4">
      <h1 className="text-3xl font-bold mb-4">Pipeline</h1>
      <p className="mb-4">Aktuelle Aufgaben der Pipeline.</p>
      <Card>
        <CardContent className="p-4">
          <h2 className="flex items-center gap-2 text-lg mb-2">
            <Target /> Define Purpose
          </h2>
          {error && <p className="text-red-600 mb-2">{error}</p>}
          <form onSubmit={(e) => e.preventDefault()} className="flex items-center gap-2">
            <input
              type="text"
              value={purposeInput}
              onChange={(e) => setPurposeInput(e.target.value)}
              placeholder="Enter project purpose..."
              className="flex-1"
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
        <Card>
          <CardContent className="p-4">
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <FileText /> Architect Seed
            </h2>
            <pre className="text-sm whitespace-pre-wrap">{blueprint}</pre>
          </CardContent>
        </Card>
      )}
      <div style={{ width: "100%", height: 700, background: "#f8fafc", borderRadius: 18, boxShadow: "0 8px 32px #000a" }}>
        {elements.length === 0 ? (
          <p className="text-center pt-8 text-slate-600">No tasks to display</p>
        ) : (
          <ReactFlow elements={elements} onNodeClick={handleNodeClick} fitView>
            <MiniMap
              nodeStrokeColor={(n) => (n.style?.border as string) ?? "#64748b"}
              nodeColor={(n) => (n.style?.background as string) ?? "#e2e8f0"}
            />
            <Controls />
            <Background color="#e2e8f0" gap={18} />
          </ReactFlow>
        )}
      </div>
      <Card className="max-h-64 overflow-auto">
        <CardContent className="p-4">
          <h2 className="flex items-center gap-2 text-lg mb-2">
            <Package /> Artifacts
          </h2>
          <ul className="space-y-1 text-sm">
            {artifacts.map((a) => (
              <li key={a.id} className="border-b border-slate-200 py-1">
                <span className="text-amber-600 font-mono mr-2">{a.task_id}</span>
                {a.repo_path}{" "}
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
      {tasks.length === 0 && (
        <div className="text-red-600 mt-4">Keine Aufgaben in der Pipeline.</div>
      )}
      {selectedTask && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={closeModal}>
          <div className="bg-white text-slate-900 p-6 rounded max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-xl font-semibold mb-2">{selectedTask.description}</h3>
            <p className="mb-1">
              <span className="font-medium">Status:</span> {selectedTask.status}
            </p>
            {selectedTask.owner && (
              <p className="mb-1">
                <span className="font-medium">Owner:</span> {selectedTask.owner}
              </p>
            )}
            {selectedTask.business_value !== undefined && (
              <p className="mb-1">
                <span className="font-medium">Business Value:</span> {selectedTask.business_value}
              </p>
            )}
            {(selectedTask.tokens_plan !== undefined || selectedTask.tokens_actual !== undefined) && (
              <p className="mb-1">
                <span className="font-medium">Tokens (plan/actual):</span> {selectedTask.tokens_plan ?? "-"} / {selectedTask.tokens_actual ?? "-"}
              </p>
            )}
            {selectedTask.notes && (
              <p className="mb-1">
                <span className="font-medium">Notes:</span> {selectedTask.notes}
              </p>
            )}
            <div className="mt-2">
              <p className="font-medium">Artifacts:</p>
              {artifacts.filter((art) => art.task_id === selectedTask.id).length === 0 ? (
                <p className="italic text-sm">No artifact</p>
              ) : (
                <ul className="list-disc list-inside text-sm">
                  {artifacts.filter((art) => art.task_id === selectedTask.id).map((artifact) => {
                    const displayPath = artifact.repo_path.replace(/^[^/]+\//, "");
                    return (
                      <li key={artifact.id}>
                        <a href={artifact.url} className="text-amber-600 hover:underline" target="_blank" rel="noopener noreferrer">
                          {displayPath}
                        </a>{" "}
                        <span className="text-xs text-slate-600">({artifact.media_type})</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <button onClick={closeModal} className="mt-4 px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded text-gray-800">
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
