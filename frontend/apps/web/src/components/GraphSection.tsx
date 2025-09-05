import PipelineGraph from './PipelineGraph';

interface GraphNode {
  id: string;
  data: { label: string; status?: string };
  position: { x: number; y: number };
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
}

interface GraphSectionProps {
  statusIcon: React.ReactNode;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export default function GraphSection({ statusIcon, nodes, edges }: GraphSectionProps) {
  return (
    <section className="mb-6">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <span>{statusIcon}</span>
        Task Dependency Graph
      </h2>
      <PipelineGraph nodes={nodes} edges={edges} />
    </section>
  );
}

