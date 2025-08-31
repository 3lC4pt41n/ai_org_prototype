import React, { useEffect } from "react";
import usePipelineStore from "../store/pipelineStore";
import PurposeSelector from "../components/PurposeSelector";
import PipelineGraph from "../components/PipelineGraph";
import ArtifactList from "../components/ArtifactList";
import ArtifactContent from "../components/ArtifactContent";
import BacklogList from "../components/BacklogList";

export default function PipelineView() {
  const { fetchPurposes, graphNodes, graphEdges, pauseAll, resumeAll } = usePipelineStore();

  useEffect(() => {
    fetchPurposes();
  }, [fetchPurposes]);

  return (
    <div className="p-4">
      <PurposeSelector />
      <div className="flex space-x-4">
        <div className="flex-1">
          <PipelineGraph nodes={graphNodes} edges={graphEdges} />
        </div>
        <div className="w-1/3 space-y-4">
          <BacklogList />
          <ArtifactList />
        </div>
      </div>
      <ArtifactContent />
      <div className="mt-4 flex justify-end space-x-2">
        <button
          className="px-3 py-1 bg-red-500 text-white rounded"
          onClick={pauseAll}
        >
          Pause alle
        </button>
        <button
          className="px-3 py-1 bg-green-500 text-white rounded"
          onClick={resumeAll}
        >
          Start alle
        </button>
      </div>
    </div>
  );
}
