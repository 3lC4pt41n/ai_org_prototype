import { useState, useEffect, useMemo } from 'react';
import usePipelineStore from '../store/pipelineStore';
import ArtifactList from '../components/ArtifactList';
// NOTE: Debug-/Isolation-Tools, um White Screen Ursachen zu finden
import BacklogList from '../components/BacklogList';
import FeedbackSection from '../components/FeedbackSection';
import PurposeSelector from '../components/PurposeSelector';

// Minimale DTOs, passend zu den API-Responses des Stores
type BacklogItem = {
  id: string;
  name: string;
  status: string;
};

type ArtifactItem = {
  id: string;
  name?: string;
  repo_path?: string;
  url?: string;
  created_at?: string;
  media_type?: string;
};

interface Task {
  id: string;
  phase: string;
  description: string;
  status: string;
  artifactUrl?: string;
}

export default function PipelineView() {
  const [paused, setPaused] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [showSidePanels, setShowSidePanels] = useState(true);
  const [useMock, setUseMock] = useState(false);
  const {
    backlog,
    artifacts,
    fetchPurposes,
    setSelectedPurpose,
    isLoading,
    selectedPurposeId,
    fetchBacklog,
    fetchArtifacts,
    fetchGraphAndStatus,
    error,
  } = usePipelineStore((state) => ({
    backlog: state.backlog as BacklogItem[],
    artifacts: state.artifacts as ArtifactItem[],
    fetchPurposes: state.fetchPurposes,
    setSelectedPurpose: state.setSelectedPurpose,
    isLoading: state.isLoading,
    selectedPurposeId: state.selectedPurposeId,
    fetchBacklog: state.fetchBacklog,
    fetchArtifacts: state.fetchArtifacts,
    fetchGraphAndStatus: state.fetchGraphAndStatus,
    error: state.error,
  }));

  // Beim ersten Render: Purposes laden und ggf. ersten auto-selektieren
  useEffect(() => {
    (async () => {
      await fetchPurposes();
      const st = usePipelineStore.getState();
      if (!st.selectedPurposeId && st.purposes.length > 0) {
        setSelectedPurpose(st.purposes[0].id);
      }
    })();
  }, [fetchPurposes, setSelectedPurpose]);

  // Daten nach Purpose-Wechsel laden
  useEffect(() => {
    if (!selectedPurposeId) return;
    fetchBacklog();
    fetchArtifacts();
    fetchGraphAndStatus(selectedPurposeId);
  }, [selectedPurposeId, fetchBacklog, fetchArtifacts, fetchGraphAndStatus]);
  // Guards: sichere Arrays verwenden, um React Error #185 zu vermeiden
  const safeBacklog: BacklogItem[] = Array.isArray(backlog) ? backlog : [];
  const safeArtifacts: ArtifactItem[] = Array.isArray(artifacts) ? artifacts : [];

  const tasksRaw: Task[] = safeBacklog.map((t: BacklogItem) => ({
    id: t.id,
    phase: t.status,
    description: t.name,
    status: t.status,
  }));

  const mockTasks: Task[] = useMemo(
    () => [
      { id: 'm1', phase: 'PRD', description: 'Mock PRD', status: 'doing' },
      { id: 'm2', phase: 'Architektur', description: 'Mock Arch', status: 'todo' },
      { id: 'm3', phase: 'Build', description: 'Mock Build', status: 'todo' },
    ],
    [],
  );

  const tasks = useMock ? mockTasks : tasksRaw;
  const artifactList = safeArtifacts.map((a: ArtifactItem) => {
    const file =
      typeof a.repo_path === 'string' ? a.repo_path.split('/').pop() || a.id : (a.name ?? a.id);
    const link = a.url ?? `/api/artifact/${a.id}`;
    return {
      name: file,
      url: link,
      created_at: a.created_at,
      media_type: a.media_type,
    };
  });

  useEffect(() => {
    // Sichtbares Logging im Dev-Console
    console.log('[PipelineView] state =', {
      selectedPurposeId,
      isLoading,
      backlog,
      artifacts,
      error,
      tasksLen: tasks?.length,
    });
  }, [selectedPurposeId, isLoading, backlog, artifacts, error, tasks?.length]);

  return (
    <div className="flex flex-col h-screen">
      {/* Steuerung */}
      <div className="p-4 bg-gray-100 flex justify-between items-center gap-2">
        <PurposeSelector />
        <div className="flex items-center gap-2">
          <button className="btn-primary" onClick={() => setPaused(!paused)}>
            {paused ? 'Fortsetzen' : 'Pause'}
          </button>
          <button className="px-2 py-1 border rounded" onClick={() => setShowDebug((v) => !v)}>
            {showDebug ? 'Debug aus' : 'Debug an'}
          </button>
          {showDebug && (
            <>
              <button
                className="px-2 py-1 border rounded"
                onClick={() => setShowSidePanels((v) => !v)}
              >
                {showSidePanels ? 'Sidepanels aus' : 'Sidepanels an'}
              </button>
              <button className="px-2 py-1 border rounded" onClick={() => setUseMock((v) => !v)}>
                {useMock ? 'Mock aus' : 'Mock an'}
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 border-b">
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </div>
      )}

      {/* Debug Panel */}
      {showDebug && (
        <div className="p-3 text-xs bg-slate-50 border-b font-mono whitespace-pre-wrap">
          <div>
            <b>selectedPurposeId:</b> {String(selectedPurposeId)}
          </div>
          <div>
            <b>isLoading:</b> {String(isLoading)}
          </div>
          <div>
            <b>tasks.length:</b> {Array.isArray(tasks) ? tasks.length : 'n/a'}
          </div>
          <div>
            <b>backlog type:</b> {Array.isArray(backlog) ? 'array' : typeof backlog}
          </div>
          <div>
            <b>artifacts type:</b> {Array.isArray(artifacts) ? 'array' : typeof artifacts}
          </div>
          <div>
            <b>error:</b> {typeof error === 'string' ? error : JSON.stringify(error)}
          </div>
        </div>
      )}

      {/* Hauptbereich: Phasenkaskade und Seitenpanel */}
      <div className="flex flex-1">
        {/* Zentrale Phasenkaskade */}
        <div className="flex-1 p-4">
          {isLoading ? (
            <p className="text-gray-500">Lade...</p>
          ) : tasks.length === 0 ? (
            <p className="text-gray-500">
              Noch keine Tasks vorhanden. Bitte einen Zweck auswählen.
            </p>
          ) : (
            // Wenn das sichtbar ist, liegt der Fehler in PhaseCascade/Props
            <ul className="list-disc pl-6 text-sm">
              {tasks.map(t => (
                <li key={t.id}>
                  {t.description} <span className="text-xs text-slate-500">({t.status})</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Artefakte und Backlog */}
        {showSidePanels && (
          <aside className="w-64 p-4 bg-gray-50 border-l">
            <ArtifactList artifacts={artifactList} />
            <BacklogList tasks={tasks.filter((t) => t.status === 'todo')} />
          </aside>
        )}
      </div>

      {/* Feedbackeingabe (nur sichtbar bei Pause) */}
      {paused && (
        <div className="p-4 bg-yellow-50 border-t">
          <FeedbackSection tasks={tasks.filter((t) => ['PRD', 'Architektur'].includes(t.phase))} />
        </div>
      )}
    </div>
  );
}
