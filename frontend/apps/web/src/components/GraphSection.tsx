import React from "react";
import PipelineGraph from "./PipelineGraph";

interface GraphSectionProps {
  statusIcon: React.ReactNode;
  nodes: Array<{
    id: string;
    data: { label: string; status?: string };
    position: { x: number; y: number };
  }>;
  edges: Array<{ id: string; source: string; target: string }>;
}

export default function GraphSection({
  statusIcon,
  nodes,
  edges,
}: GraphSectionProps) {
  return (
    <section className="p-4">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <span>{statusIcon}</span> Task Dependency Graph
      </h2>
      <PipelineGraph nodes={nodes} edges={edges} />
    </section>
  );
}

