// src/pages/TaskGraph.jsx
import React, { useEffect, useState } from "react";
import ReactFlow, { MiniMap, Controls, Background } from "reactflow";
import "reactflow/dist/style.css";

function statusColor(status) {
  switch (status) {
    case "done": return "#22c55e";
    case "doing": return "#fbbf24";
    case "failed": return "#ef4444";
    default: return "#64748b";
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
                  <i>Status: {task.status}</i>
                </div>
              </div>
            )
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
            fontWeight: 500
          }
        }));
        const edges = data.dependencies.map(dep => ({
          id: `${dep.from_id}->${dep.to_id}`,
          source: dep.from_id,
          target: dep.to_id
        }));
        setElements([...nodes, ...edges]);
      });
  }, []);

  return (
    <div style={{ width: "100%", height: 700, background: "#0f172a", borderRadius: 18, marginTop: 32, boxShadow: "0 8px 32px #000a" }}>
      <ReactFlow elements={elements} fitView>
        <MiniMap nodeStrokeColor={n => n.style?.border ?? "#64748b"} nodeColor={n => n.style?.background ?? "#334155"} />
        <Controls />
        <Background color="#334155" gap={18} />
      </ReactFlow>
    </div>
  );
}
