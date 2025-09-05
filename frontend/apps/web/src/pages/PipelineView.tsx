import { useState, useEffect } from 'react';
import usePipelineStore from '../store/pipelineStore';
import PurposeSelector from '../components/PurposeSelector';
import ArtifactSection from '../components/ArtifactSection';
import GraphSection from '../components/GraphSection';

interface ArtifactItem {
  id: string;
  repo_path?: string;
  url?: string;
  created_at?: string;
  media_type?: string;
}

export default function PipelineView() {
  const [paused, setPaused] = useState(false);
  const artifacts = usePipelineStore((s) => s.artifacts) as ArtifactItem[];
  const purposes = usePipelineStore((s) => (s as any).purposes ?? []);
  const graphNodes = usePipelineStore((s) => s.graphNodes);
  const graphEdges = usePipelineStore((s) => s.graphEdges);
  const isLoading = usePipelineStore((s) => s.isLoading);
  const error = usePipelineStore((s) => s.error);
  const selectedPurposeId = usePipelineStore((s) => s.selectedPurposeId);
  const fetchPurposes = usePipelineStore((s) => s.fetchPurposes);
  const setSelectedPurpose = usePipelineStore((s) => s.setSelectedPurpose);
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);

  // load purposes on mount
  useEffect(() => {
    fetchPurposes();
  }, [fetchPurposes]);

  // auto select first purpose
  useEffect(() => {
    if (!selectedPurposeId && purposes.length > 0) {
      setSelectedPurpose(purposes[0].id);
    }
  }, [purposes, selectedPurposeId, setSelectedPurpose]);

  // load artifacts and graph on purpose change
  useEffect(() => {
    if (!selectedPurposeId) return;
    const controller = new AbortController();
    const signal = controller.signal;
    fetchArtifacts(signal);
    fetchGraphAndStatus(selectedPurposeId, signal);
    return () => controller.abort();
  }, [selectedPurposeId, fetchArtifacts, fetchGraphAndStatus]);

  const safeArtifacts: ArtifactItem[] = Array.isArray(artifacts) ? artifacts : [];
  const prdArtifact = safeArtifacts.find((a) =>
    a.repo_path?.toLowerCase().includes('product_requirements')
  );
  const archArtifact = safeArtifacts.find((a) =>
    a.repo_path?.toLowerCase().includes('architecture_blueprint')
  );

  const prdStatusIcon = paused && !archArtifact ? '🕓' : '✅';
  const archStatusIcon = paused && archArtifact ? '🕓' : '✅';
  const graphStatusIcon = paused ? '🕓' : '✅';

  return (
    <div className="flex flex-col h-screen">
      <div className="p-4 bg-gray-100 flex justify-between items-center gap-2">
        <PurposeSelector />
        <button className="btn-primary" onClick={() => setPaused(!paused)}>
          {paused ? 'Fortsetzen' : 'Pause'}
        </button>
      </div>
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 border-b">
          {typeof error === 'string'
            ? error
            : error instanceof Error
            ? error.message
            : String(error)}
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
                showFeedback={paused && !archArtifact}
              />
            )}
            {archArtifact && (
              <ArtifactSection
                title="Architektur"
                artifact={archArtifact}
                statusIcon={archStatusIcon}
                showFeedback={paused && !!archArtifact}
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

