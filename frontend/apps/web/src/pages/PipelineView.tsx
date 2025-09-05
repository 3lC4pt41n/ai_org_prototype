import { useEffect } from "react";
import usePipelineStore from "../store/pipelineStore";
import PurposeSelector from "../components/PurposeSelector";
import ArtifactSection from "../components/ArtifactSection";
import GraphSection from "../components/GraphSection";

interface ArtifactItem {
  id: string;
  repo_path?: string;
  url?: string;
  created_at?: string;
  media_type?: string;
}

export default function PipelineView() {
  const artifacts = usePipelineStore((s) => s.artifacts) as ArtifactItem[];
  const purposes = usePipelineStore((s) => (s as any).purposes ?? []);
  const graphNodes = usePipelineStore((s) => s.graphNodes);
  const graphEdges = usePipelineStore((s) => s.graphEdges);
  const paused = usePipelineStore((s) => s.paused);
  const isLoading = usePipelineStore((s) => s.isLoading);
  const error = usePipelineStore((s) => s.error);
  const selectedPurposeId = usePipelineStore((s) => s.selectedPurposeId);
  const fetchPurposes = usePipelineStore((s) => s.fetchPurposes);
  const setSelectedPurpose = usePipelineStore((s) => s.setSelectedPurpose);
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);

  useEffect(() => {
    fetchPurposes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchPurposes]);

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

  const prdArtifact = artifacts.find(a => a.repo_path?.toLowerCase().includes('product_requirements_document'));
  const archArtifact = artifacts.find(a => a.repo_path?.toLowerCase().includes('architecture_blueprint'));

  const prdPending  = paused && !archArtifact;
  const archPending = paused && !!archArtifact;
  const prdStatusIcon  = prdPending  ? '🕓' : '✅';
  const archStatusIcon = archArtifact ? (archPending ? '🕓' : '✅') : '✅';
  const graphStatusIcon = paused ? '🕓' : '✅';

  return (
    <div className="flex flex-col h-screen">
      <div className="p-4 bg-gray-100 flex justify-between items-center gap-2">
        <PurposeSelector />
        {/* Pause/Resume handled in AdminDashboard; hier nur Anzeige */}
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 border-b">
          {typeof error === 'string' ? error : error instanceof Error ? error.message : String(error)}
        </div>
      )}

      <div className="main-panel flex-1 overflow-y-auto p-4">
        {isLoading && <p className="text-gray-500">Lade...</p>}
        {!isLoading && (
          <>
            {prdArtifact && (
              <ArtifactSection
                title="Product Requirements Document"
                artifact={prdArtifact}
                statusIcon={prdStatusIcon}
                showFeedback={prdPending}
              />
            )}
            {archArtifact && (
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
          </>
        )}
      </div>
    </div>
  );
}

