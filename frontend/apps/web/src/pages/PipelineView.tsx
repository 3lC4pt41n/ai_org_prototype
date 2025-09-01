import React, { useState, useEffect } from "react";
import usePipelineStore from "../store/pipelineStore";
import PhaseCascade from "../components/PhaseCascade";
import ArtifactList from "../components/ArtifactList";
import BacklogList from "../components/BacklogList";
import FeedbackSection from "../components/FeedbackSection";
import PurposeSelector from "../components/PurposeSelector";

interface Task {
  id: string;
  phase: string;
  description: string;
  status: string;
  artifactUrl?: string;
}

export default function PipelineView() {
  const [paused, setPaused] = useState(false);
  const {
    backlog,
    artifacts,
    fetchPurposes,
    setSelectedPurpose,
    isLoading,
  } = usePipelineStore((state) => ({
    backlog: state.backlog,
    artifacts: state.artifacts,
    fetchPurposes: state.fetchPurposes,
    setSelectedPurpose: state.setSelectedPurpose,
    isLoading: state.isLoading,
  }));

  useEffect(() => {
    const init = async () => {
      await fetchPurposes();
      const { purposes, selectedPurposeId } = usePipelineStore.getState();
      if (purposes.length > 0 && !selectedPurposeId) {
        setSelectedPurpose(purposes[0].id);
      }
    };
    void init();
  }, [fetchPurposes, setSelectedPurpose]);

  const tasks: Task[] = backlog.map((t) => ({
    id: t.id,
    phase: t.status,
    description: t.name,
    status: t.status,
  }));

  const artifactList = artifacts.map((a) => ({ name: a.name, url: a.id }));

  return (
    <div className="flex flex-col h-screen">
      {/* Steuerung */}
      <div className="p-4 bg-gray-100 flex justify-between items-center">
        <PurposeSelector />
        <button className="btn-primary" onClick={() => setPaused(!paused)}>
          {paused ? "Fortsetzen" : "Pause"}
        </button>
      </div>

      {/* Hauptbereich: Phasenkaskade und Seitenpanel */}
      <div className="flex flex-1">
        {/* Zentrale Phasenkaskade */}
        <div className="flex-1 p-4">
          {isLoading ? (
            <p className="text-gray-500">Lade...</p>
          ) : backlog.length === 0 ? (
            <p className="text-gray-500">
              Noch keine Tasks vorhanden. Bitte einen Zweck auswählen.
            </p>
          ) : (
            <PhaseCascade tasks={tasks} paused={paused} />
          )}
        </div>

        {/* Artefakte und Backlog */}
        <aside className="w-64 p-4 bg-gray-50 border-l">
          <ArtifactList artifacts={artifactList} />
          <BacklogList tasks={tasks.filter((t) => t.status === "todo")} />
        </aside>
      </div>

      {/* Feedbackeingabe (nur sichtbar bei Pause) */}
      {paused && (
        <div className="p-4 bg-yellow-50 border-t">
          <FeedbackSection
            tasks={tasks.filter((t) => ["PRD", "Architektur"].includes(t.phase))}
          />
        </div>
      )}
    </div>
  );
}
