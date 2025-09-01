import React, { useState } from "react";
import usePipelineStore from "../store/pipelineStore";
import PhaseCascade from "../components/PhaseCascade";
import ArtifactList from "../components/ArtifactList";
import BacklogList from "../components/BacklogList";
import FeedbackSection from "../components/FeedbackSection";

interface Task {
  id: string;
  phase: string;
  description: string;
  status: string;
  artifactUrl?: string;
}

export default function PipelineView() {
  const [paused, setPaused] = useState(false);
  const { backlog, artifacts } = usePipelineStore((state) => ({
    backlog: state.backlog,
    artifacts: state.artifacts,
  }));

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
      <div className="p-4 bg-gray-100 flex justify-end">
        <button className="btn-primary" onClick={() => setPaused(!paused)}>
          {paused ? "Fortsetzen" : "Pause"}
        </button>
      </div>

      {/* Hauptbereich: Phasenkaskade und Seitenpanel */}
      <div className="flex flex-1">
        {/* Zentrale Phasenkaskade */}
        <div className="flex-1 p-4">
          <PhaseCascade tasks={tasks} paused={paused} />
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

