import React from "react";
import ReactFlow, { Controls, Background } from "reactflow";
import "reactflow/dist/style.css";

console.log("Loading PipelineGraph module");

interface PipelineGraphProps {
  nodes: Array<{
    id: string;
    data: { label: string; status?: string };
    position: { x: number; y: number };
  }>;
  edges: Array<{ id: string; source: string; target: string }>;
}

export default function PipelineGraph({ nodes, edges }: PipelineGraphProps) {
  return (
    <div className="border rounded p-2 h-96">
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Controls />
        <Background gap={16} />
      </ReactFlow>
    </div>
  );
}
