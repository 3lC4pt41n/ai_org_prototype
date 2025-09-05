import { useEffect } from "react";
import usePipelineStore from "../store/pipelineStore";
import ArtifactList from "../components/ArtifactList";
import BacklogList from "../components/BacklogList";
import PurposeSelector from "../components/PurposeSelector";
import ArtifactSection from "../components/ArtifactSection";
import GraphSection from "../components/GraphSection";

type BacklogItem = {
  id: string;
  name: string;
  status: string;
};

type ArtifactItem = {
  id: string;
  repo_path?: string;
  url?: string;
  created_at?: string;
  media_type?: string;
  task_desc?: string;
};

export default function PipelineView() {
  const backlog = usePipelineStore((s) => s.backlog) as BacklogItem[];
  const artifacts = usePipelineStore((s) => s.artifacts) as ArtifactItem[];
  const purposes = usePipelineStore((s) => (s as any).purposes ?? []);
  const graphNodes = usePipelineStore((s) => s.graphNodes);
  const graphEdges = usePipelineStore((s) => s.graphEdges);
  const tasksStatus = usePipelineStore((s) => s.tasksStatus);
  const paused = usePipelineStore((s) => s.paused);
  const isLoading = usePipelineStore((s) => s.isLoading);
  const error = usePipelineStore((s) => s.error);
  const selectedPurposeId = usePipelineStore((s) => s.selectedPurposeId);
  const fetchPurposes = usePipelineStore((s) => s.fetchPurposes);
  const setSelectedPurpose = usePipelineStore((s) => s.setSelectedPurpose);
  const fetchBacklog = usePipelineStore((s) => s.fetchBacklog);
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);
  const pausePurpose = usePipelineStore((s) => s.pausePurpose);
  const startPurpose = usePipelineStore((s) => s.startPurpose);

  useEffect(() => {
    fetchPurposes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedPurposeId && Array.isArray(purposes) && purposes.length > 0) {
      setSelectedPurpose(purposes[0].id);
    }
  }, [purposes, selectedPurposeId, setSelectedPurpose]);

  useEffect(() => {
    if (!selectedPurposeId) return;
    const controller = new AbortController();
    const signal = controller.signal;
    fetchBacklog(signal);
    fetchArtifacts(signal);
    fetchGraphAndStatus(selectedPurposeId, signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPurposeId]);

  const safeBacklog: BacklogItem[] = Array.isArray(backlog) ? backlog : [];
  const safeArtifacts: ArtifactItem[] = Array.isArray(artifacts) ? artifacts : [];

  const artifactList = safeArtifacts.map((a) => {
    const file =
      typeof a.repo_path === "string"
        ? a.repo_path.split("/").pop() || a.id
        : a.id;
    const link = a.url ?? `/api/artifact/${a.id}`;
    return { name: file, url: link, created_at: a.created_at, media_type: a.media_type };
  });

  const backlogList = safeBacklog.map((t) => ({ id: t.id, description: t.name }));

  const prdArtifact = safeArtifacts.find(
    (a) => a.task_desc === "Product Requirements Document"
  );
  const archArtifact = safeArtifacts.find(
    (a) => a.task_desc === "Architecture Blueprint"
  );

  const prdPending = paused && !archArtifact;
  const archPending = paused && !!archArtifact;
  const prdStatusIcon = prdPending ? "🕓" : "✅";
  const archStatusIcon = archArtifact ? (archPending ? "🕓" : "✅") : null;
  const tasksComplete = Object.values(tasksStatus || {}).every((s) => s === "done");
  const graphStatusIcon = tasksComplete ? "✅" : "🕓";

  const handlePauseToggle = async () => {
    if (!selectedPurposeId) return;
    if (paused) {
      await startPurpose(selectedPurposeId);
    } else {
      await pausePurpose(selectedPurposeId);
    }
    await fetchGraphAndStatus(selectedPurposeId);
  };

  return (
    <div className="flex flex-col h-screen">
      <div className="p-4 bg-gray-100 flex justify-between items-center gap-2">
        <PurposeSelector />
        <button className="btn-primary" onClick={handlePauseToggle}>
          {paused ? "Fortsetzen" : "Pause"}
        </button>
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 border-b">
          {typeof error === "string"
            ? error
            : error instanceof Error
            ? error.message
            : String(error)}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {prdArtifact && (
            <ArtifactSection
              title="Product Requirements Document"
              artifact={prdArtifact}
              statusIcon={prdStatusIcon}
              showFeedback={prdPending}
            />
          )}
          {archArtifact && archStatusIcon && (
            <ArtifactSection
              title="Architektur"
              artifact={archArtifact}
              statusIcon={archStatusIcon}
              showFeedback={archPending}
            />
          )}
          <GraphSection
            statusIcon={graphStatusIcon}
            nodes={graphNodes}
            edges={graphEdges}
          />
          {isLoading && (
            <p className="text-sm text-gray-500">Lade Daten...</p>
          )}
        </div>
        <aside className="w-64 p-4 bg-gray-50 border-l overflow-y-auto">
          <ArtifactList artifacts={artifactList} />
          <BacklogList tasks={backlogList} />
        </aside>
      </div>
    </div>
  );
}

