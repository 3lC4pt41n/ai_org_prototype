// src/pages/TaskGraph.jsx
import React, { useEffect, useState } from "react";
import ReactFlow, { MiniMap, Controls, Background } from "reactflow";
import { toast } from "react-hot-toast";
import "reactflow/dist/style.css";
function statusColor(status: string) {
  switch (status) {
    case "done":
      return "#22c55e";
    case "doing":
      return "#3b82f6";
    case "failed":
      return "#ef4444";
    case "blocked":
    case "skipped":
    case "budget_exceeded":
      return "#64748b";
    default:
      return "#64748b";
  }
}

function getStatusTooltip(status: string, owner?: string): string {
  if (status === "failed" && owner === "QA") {
    return "QA failed – automated tests did not pass.";
  }
  switch (status) {
    case "todo":
      return "Task not started yet.";
    case "doing":
      return "Task in progress.";
    case "done":
      return "Task completed successfully.";
    case "failed":
      return "Task execution failed.";
    case "blocked":
      return "Task blocked (prerequisites not met or budget).";
    case "budget_exceeded":
      return "Task not executed due to budget limit.";
    case "skipped":
      return "Task was skipped (not executed).";
    default:
      return "";
  }
}

// Bubblegröße dynamisch skalieren (Business Value oder PlanToken)
function getNodeSize(task) {
  // Skaliere mit log() damit große Werte nicht explodieren
  // Min=40px, Max=140px
  const base = 40;
  const max = 140;
  const bv = task.business_value ?? 1;
  const scale = Math.log2(bv + 1) * 25 + base;
  return Math.max(base, Math.min(scale, max));
}

export default function TaskGraph() {
  const [elements, setElements] = useState([]);

  useEffect(() => {
    fetch("/api/graph", {
      headers: { Authorization: `Bearer ${localStorage.getItem("token") || ""}` }
    })
      .then(r => r.json())
      .then(data => {
        const nodes = data.tasks.map(task => ({
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
                  <i>
                    Status: {" "}
                    <span title={getStatusTooltip(task.status, task.owner)}>
                      {task.status}
                    </span>
                  </i>
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
        const edges = data.dependencies.map(dep => ({
          id: `${dep.from_id}->${dep.to_id}`,
          source: dep.from_id,
          target: dep.to_id
        }));
        setElements([...nodes, ...edges]);
      })
      .catch(() => {
        toast.error("Failed to load task graph.");
      });
  }, []);

  return (
    <div className="min-h-screen p-4">
      <h1 className="text-3xl font-bold mb-4">Graph</h1>
      <p className="mb-4">Visualisierung aller Aufgaben im Graph-Format.</p>
      <div style={{ width: "100%", height: 700, background: "#f8fafc", borderRadius: 18, marginTop: 32, boxShadow: "0 8px 32px #000a" }}>
        <ReactFlow elements={elements} fitView>
          <MiniMap nodeStrokeColor={n => n.style?.border ?? "#64748b"} nodeColor={n => n.style?.background ?? "#e2e8f0"} />
          <Controls />
          <Background color="#e2e8f0" gap={18} />
        </ReactFlow>
      </div>
      {elements.length === 0 && (
        <div className="text-red-600 mt-4">Keine Aufgaben generiert.</div>
      )}
    </div>
  );
}
