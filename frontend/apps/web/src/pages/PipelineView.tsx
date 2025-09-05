import { useEffect } from "react";
import ArtifactSection from "../components/ArtifactSection";
import GraphSection from "../components/GraphSection";
import PurposeSelector from "../components/PurposeSelector";
import usePipelineStore from "../store/pipelineStore";

export default function PipelineView() {
  const artifacts = usePipelineStore((s) => s.artifacts);
  const graphNodes = usePipelineStore((s) => s.graphNodes);
  const graphEdges = usePipelineStore((s) => s.graphEdges);
  const tasksStatus = usePipelineStore((s) => s.tasksStatus);
  const paused = usePipelineStore((s) => s.paused);
  const purposes = usePipelineStore((s) => s.purposes);
  const selectedPurposeId = usePipelineStore((s) => s.selectedPurposeId);
  const fetchPurposes = usePipelineStore((s) => s.fetchPurposes);
  const setSelectedPurpose = usePipelineStore((s) => s.setSelectedPurpose);
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);
  const pausePurpose = usePipelineStore((s) => s.pausePurpose);
  const startPurpose = usePipelineStore((s) => s.startPurpose);

  useEffect(() => {
    fetchPurposes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedPurposeId && purposes.length > 0) {
      setSelectedPurpose(purposes[0].id);
    }
  }, [purposes, selectedPurposeId, setSelectedPurpose]);

  useEffect(() => {
    if (!selectedPurposeId) return;
    const controller = new AbortController();
    const signal = controller.signal;
    fetchArtifacts(signal);
    fetchGraphAndStatus(selectedPurposeId, signal);
    return () => controller.abort();
  }, [selectedPurposeId, fetchArtifacts, fetchGraphAndStatus]);

  const prdArtifact = artifacts.find(
    (a) => a.task_desc === "Product Requirements Document"
  );
  const archArtifact = artifacts.find(
    (a) => a.task_desc === "Architecture Blueprint"
  );

  const prdPending = paused && !!prdArtifact && !archArtifact;
  const archPending = paused && !!archArtifact;
  const graphPending = Object.values(tasksStatus).some((s) => s !== "done");

  const togglePause = () => {
    if (!selectedPurposeId) return;
    if (paused) {
      startPurpose(selectedPurposeId);
    } else {
      pausePurpose(selectedPurposeId);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <div className="p-4 bg-gray-100 flex justify-between items-center">
        <PurposeSelector />
        <button className="btn-primary" onClick={togglePause}>
          {paused ? "Fortsetzen" : "Pause"}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {prdArtifact && (
          <ArtifactSection
            title="Product Requirements Document"
            artifact={prdArtifact}
            statusIcon={prdPending ? "🕓" : "✅"}
            showFeedback={paused && !archArtifact}
          />
        )}
        {archArtifact && (
          <ArtifactSection
            title="Architektur"
            artifact={archArtifact}
            statusIcon={archPending ? "🕓" : "✅"}
            showFeedback={paused && !!archArtifact}
          />
        )}
        <GraphSection
          statusIcon={graphPending ? "🕓" : "✅"}
          nodes={graphNodes}
          edges={graphEdges}
        />
      </div>
    </div>
  );
}

