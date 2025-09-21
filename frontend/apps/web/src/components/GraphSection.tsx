import PipelineGraph from "./PipelineGraph";

console.log("Loading GraphSection module");

interface Props {
  statusIcon: React.ReactNode;
  nodes: Array<{
    id: string;
    data: { label: string; status?: string };
    position: { x: number; y: number };
  }>;
  edges: Array<{ id: string; source: string; target: string }>;
}

export default function GraphSection({ statusIcon, nodes, edges }: Props) {
  return (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-700 dark:text-slate-200">
          <span>{statusIcon}</span>
          Task-Abhängigkeitsgraph
        </h2>
        <p className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">
          {nodes.length} Knoten · {edges.length} Kanten
        </p>
      </div>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
        Visualisiere Abhängigkeiten und identifiziere kritische Pfade innerhalb der Implementierung.
      </p>
      <div className="mt-4">
        <PipelineGraph nodes={nodes} edges={edges} />
      </div>
    </section>
  );
}

