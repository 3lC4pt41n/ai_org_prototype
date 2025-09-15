import { useEffect, useMemo, useRef, useState } from 'react';
import {
  History,
  Package,
  Lightbulb,
  FileText,
  CircuitBoard,
  Hammer,
  ClipboardCheck,
  CheckCircle2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { toast } from 'react-hot-toast';
import usePipelineStore from '../store/pipelineStore';
import PurposeSelector from '../components/PurposeSelector';
import ArtifactSection from '../components/ArtifactSection';
import GraphSection from '../components/GraphSection';
import { API_BASE } from '../lib/api';
import AImarChatPanel from '../components/AImarChatPanel';

interface ArtifactItem {
  id: string;
  repo_path?: string;
  url?: string;
  created_at?: string;
  media_type?: string;
  released?: boolean;
  task_id?: string;
  task_desc?: string;
}

type PhaseId = 'vision' | 'prd' | 'architecture' | 'implementation' | 'review';

interface PhaseMeta {
  id: PhaseId;
  title: string;
  icon: LucideIcon;
  completed: boolean;
  index: number;
  isCurrent: boolean;
  isUpcoming: boolean;
}

const PHASE_ORDER: PhaseId[] = ['vision', 'prd', 'architecture', 'implementation', 'review'];

const PHASE_DESCRIPTIONS: Record<PhaseId, string> = {
  vision:
    'Definiere Zielsetzung und Kontext des Projekts. Wähle einen Purpose aus, um den weiteren Verlauf zu steuern.',
  prd: 'Erarbeite die Produktanforderungen und stelle sicher, dass alle Stakeholder den gleichen Stand teilen.',
  architecture:
    'Gestalte das technische Fundament. Das Architektur-Blueprint bildet die Basis für eine belastbare Implementierung.',
  implementation:
    'Arbeite die Aufgaben aus dem Task-Graph ab und kollaboriere mit dem Team entlang der Pipeline.',
  review:
    'Führe finale Abstimmungen durch, gib Deliverables frei und sichere die Übergabe in den Betrieb.',
};

export default function PipelineView() {
  const artifacts = usePipelineStore((s) => s.artifacts) as ArtifactItem[];
  const backlog = usePipelineStore((s) => s.backlog);
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
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchBacklog = usePipelineStore((s) => s.fetchBacklog);
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
    fetchBacklog(signal);
    fetchGraphAndStatus(selectedPurposeId, signal);
    return () => controller.abort();
  }, [selectedPurposeId, fetchArtifacts, fetchBacklog, fetchGraphAndStatus]);

  const prdArtifacts = artifacts.filter((a) =>
    a.repo_path?.toLowerCase().includes('product_requirements'),
  );
  const prdArtifact = prdArtifacts.length > 0 ? prdArtifacts[prdArtifacts.length - 1] : undefined;
  const archArtifact = artifacts.find((a) =>
    a.repo_path?.toLowerCase().includes('architecture_blueprint'),
  );

  const prdPending = paused && !archArtifact; // bleibt für Status-Icon Logik bestehen
  const archPending = paused && !!archArtifact;
  const prdStatusIcon = prdPending ? '🕓' : '✅';
  const archStatusIcon = archArtifact ? (archPending ? '🕓' : '✅') : '✅';
  const graphStatusIcon = paused ? '🕓' : '✅';

  const tasksStatusValues = Object.values(tasksStatus ?? {});
  const hasTasks = tasksStatusValues.length > 0;
  const allTasksDone = hasTasks && tasksStatusValues.every((status) => status === 'done');
  const backlogEmpty = backlog.length === 0;
  const releasedArtifacts = artifacts.filter((a) => a.released);
  const allArtifactsReleased = artifacts.length > 0 && releasedArtifacts.length === artifacts.length;
  const selectedPurpose = purposes.find((p) => p.id === selectedPurposeId) || null;

  const visionCompleted = Boolean(selectedPurposeId);
  const prdCompleted = Boolean(prdArtifact);
  const architectureCompleted = Boolean(archArtifact);
  const implementationCompleted = allTasksDone;
  const reviewCompleted = implementationCompleted && backlogEmpty && allArtifactsReleased;

  const recommendedPhase = useMemo<PhaseId>(() => {
    if (!visionCompleted) return 'vision';
    if (!prdCompleted) return 'prd';
    if (!architectureCompleted) return 'architecture';
    if (!implementationCompleted) return 'implementation';
    if (!reviewCompleted) return 'review';
    return 'review';
  }, [visionCompleted, prdCompleted, architectureCompleted, implementationCompleted, reviewCompleted]);

  const [currentPhase, setCurrentPhaseInternal] = useState<PhaseId>(recommendedPhase);
  const userSelectedPhaseRef = useRef(false);

  useEffect(() => {
    setCurrentPhaseInternal((prev) => {
      const prevIndex = PHASE_ORDER.indexOf(prev);
      const recommendedIndex = PHASE_ORDER.indexOf(recommendedPhase);
      if (!userSelectedPhaseRef.current || recommendedIndex > prevIndex) {
        if (recommendedIndex !== prevIndex) {
          userSelectedPhaseRef.current = false;
        }
        return recommendedPhase;
      }
      return prev;
    });
  }, [recommendedPhase]);

  const handlePhaseSelect = (phase: PhaseId) => {
    userSelectedPhaseRef.current = true;
    setCurrentPhaseInternal(phase);
  };

  const phases = useMemo<PhaseMeta[]>(() => {
    const definitions: Array<{
      id: PhaseId;
      title: string;
      icon: LucideIcon;
      completed: boolean;
    }> = [
      { id: 'vision', title: 'Vision', icon: Lightbulb, completed: visionCompleted },
      { id: 'prd', title: 'PRD', icon: FileText, completed: prdCompleted },
      { id: 'architecture', title: 'Architektur', icon: CircuitBoard, completed: architectureCompleted },
      { id: 'implementation', title: 'Implementierung', icon: Hammer, completed: implementationCompleted },
      { id: 'review', title: 'Review', icon: ClipboardCheck, completed: reviewCompleted },
    ];
    let previousCompleted = true;
    return definitions.map((phase, index) => {
      const isCurrent = currentPhase === phase.id;
      const isUpcoming = !phase.completed && !previousCompleted && !isCurrent;
      if (!phase.completed) {
        previousCompleted = false;
      }
      return {
        ...phase,
        index,
        isCurrent,
        isUpcoming,
      } satisfies PhaseMeta;
    });
  }, [visionCompleted, prdCompleted, architectureCompleted, implementationCompleted, reviewCompleted, currentPhase]);

  const currentPhaseMeta = phases.find((phase) => phase.id === currentPhase) ?? phases[0];

  const getPhaseStatusLabel = (phase: PhaseMeta) => {
    if (phase.completed) return 'Abgeschlossen';
    if (phase.isCurrent) return 'Aktive Phase';
    if (phase.isUpcoming) return 'Geplant';
    return 'Bereit';
  };

  const chatPanel = selectedPurposeId ? (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
      <AImarChatPanel purposeId={selectedPurposeId} paused={paused} />
    </section>
  ) : (
    <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
      <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Kein Purpose ausgewählt</h3>
      <p className="mt-2">
        Wähle im Kopfbereich einen Purpose aus, um Artefakte zu erstellen und mit dem KI-Produkt Owner zu
        interagieren.
      </p>
    </section>
  );

  const phaseContent = (() => {
    switch (currentPhase) {
      case 'vision':
        return (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Projektvision</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                {selectedPurpose
                  ? `Aktueller Purpose: ${selectedPurpose.name}`
                  : 'Noch kein Purpose ausgewählt. Erstelle oder aktiviere einen Purpose, um die Vision zu konkretisieren.'}
              </p>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                Nutze die Auswahl oben, um einen Purpose zu setzen. Sobald eine Vision feststeht, werden nachfolgende
                Phasen freigeschaltet.
              </p>
            </section>
            <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <h3 className="text-base font-semibold text-slate-700 dark:text-slate-200">Verfügbare Purposes</h3>
              {purposes.length > 0 ? (
                <ul className="mt-4 space-y-2 text-sm">
                  {purposes.map((purpose) => (
                    <li
                      key={purpose.id}
                      className={`flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 ${
                        purpose.id === selectedPurposeId
                          ? 'bg-amber-50 text-amber-900 dark:bg-amber-500/10'
                          : 'bg-slate-50 text-slate-700 dark:bg-slate-800/60 dark:text-slate-200'
                      }`}
                    >
                      <span className="font-medium">{purpose.name}</span>
                      {purpose.id === selectedPurposeId ? (
                        <span className="text-xs font-semibold text-amber-600">Aktiv</span>
                      ) : (
                        <span className="text-xs text-slate-500 dark:text-slate-400">Auswahl möglich</span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                  Noch keine Purposes vorhanden. Lege einen neuen Purpose an, um die Pipeline zu starten.
                </p>
              )}
            </section>
          </div>
        );
      case 'prd':
        return (
          <div className="space-y-6">
            {prdArtifact ? (
              <ArtifactSection
                title="Product Requirements Document"
                artifact={prdArtifact}
                statusIcon={prdStatusIcon}
                showFeedback={prdPending}
              />
            ) : (
              <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
                <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">PRD in Erstellung</h3>
                <p className="mt-2">
                  Sobald das Product Requirements Document generiert wurde, erscheint es hier zur Durchsicht und
                  Kommentierung.
                </p>
                <p className="mt-2">
                  Beobachte den Backlog auf der rechten Seite, um den Fortschritt der zugrunde liegenden Aufgaben zu
                  verfolgen.
                </p>
              </section>
            )}
          </div>
        );
      case 'architecture':
        return (
          <div className="space-y-6">
            {archArtifact ? (
              <ArtifactSection
                title="Architektur"
                artifact={archArtifact}
                statusIcon={archStatusIcon}
                showFeedback={archPending}
              />
            ) : (
              <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
                <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Architektur in Vorbereitung</h3>
                <p className="mt-2">
                  Das Architektur-Blueprint ist noch nicht verfügbar. Sobald die Modellierung abgeschlossen ist, kannst du
                  hier Feedback geben.
                </p>
                {prdArtifact && (
                  <p className="mt-2">
                    Das PRD liegt bereits vor und dient als Grundlage für die Architekturphase.
                  </p>
                )}
              </section>
            )}
          </div>
        );
      case 'implementation':
        return (
          <div className="space-y-6">
            {graphNodes.length > 0 ? (
              <GraphSection statusIcon={graphStatusIcon} nodes={graphNodes} edges={graphEdges} />
            ) : (
              <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
                <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Aufgaben werden vorbereitet</h3>
                <p className="mt-2">
                  Der Task-Graph steht noch nicht zur Verfügung. Sobald Aufgaben generiert wurden, erscheint der Graph in
                  dieser Phase.
                </p>
              </section>
            )}
            {chatPanel}
          </div>
        );
      case 'review':
        return (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Review-Übersicht</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                {releasedArtifacts.length > 0
                  ? `${releasedArtifacts.length} von ${artifacts.length} Artefakten sind bereits freigegeben.`
                  : 'Noch keine Artefakte wurden freigegeben. Prüfe die Ergebnisse und markiere sie als bereit für den Rollout.'}
              </p>
              <ul className="mt-4 space-y-2 text-sm">
                {artifacts.length > 0 ? (
                  artifacts.map((artifact) => {
                    const fileName = artifact.repo_path?.split('/').pop() || artifact.id;
                    return (
                      <li key={artifact.id} className="flex items-center justify-between">
                        <span className="truncate pr-2 text-slate-700 dark:text-slate-200">{fileName}</span>
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                            artifact.released
                              ? 'bg-green-100 text-green-700'
                              : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                          }`}
                        >
                          {artifact.released ? 'Freigegeben' : 'In Prüfung'}
                        </span>
                      </li>
                    );
                  })
                ) : (
                  <li className="text-slate-600 dark:text-slate-300">Noch keine Artefakte vorhanden.</li>
                )}
              </ul>
            </section>
            {chatPanel}
          </div>
        );
      default:
        return null;
    }
  })();

  const statusInfo: Record<string, { label: string; color: string }> = {
    todo: { label: 'Todo', color: 'bg-yellow-500 text-black' },
    doing: { label: 'In Progress', color: 'bg-blue-500 text-white' },
    done: { label: 'Done', color: 'bg-green-600 text-white' },
    failed: { label: 'Failed', color: 'bg-red-600 text-white' },
    blocked: { label: 'Blocked', color: 'bg-gray-500 text-white' },
    skipped: { label: 'Skipped', color: 'bg-gray-500 text-white' },
    budget_exceeded: {
      label: 'Blocked (Budget)',
      color: 'bg-gray-500 text-white',
    },
  };

  function downloadArtifactFile(artifactId: string, filename: string) {
    const token = localStorage.getItem('token');
    fetch(`${API_BASE}/artifact/${artifactId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error('Download fehlgeschlagen');
        return res.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(() => toast.error('Download fehlgeschlagen'));
  }

  return (
    <div className="flex flex-col h-screen">
      <div className="p-4 bg-gray-100 dark:bg-slate-800 flex justify-between items-center gap-2">
        <PurposeSelector />
        {paused ? (
          <span className="text-sm">
            <span className="font-medium">Status:</span>{' '}
            <span className="font-semibold text-red-600">Pausiert</span>
          </span>
        ) : (
          <span className="text-sm">
            <span className="font-medium">Status:</span>{' '}
            <span className="font-semibold text-green-600">Läuft</span>
          </span>
        )}
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-50 dark:bg-red-900 text-red-600 dark:text-red-500 border-b">
          {typeof error === 'string'
            ? error
            : error instanceof Error
              ? error.message
              : String(error)}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <nav className="w-64 flex-shrink-0 border-r border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 overflow-y-auto">
          <div className="mb-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Phasen</h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Navigiere zwischen den Arbeitsschritten der Pipeline.
            </p>
          </div>
          <ul className="space-y-2">
            {phases.map((phase) => {
              const Icon = phase.icon;
              const statusLabel = getPhaseStatusLabel(phase);
              return (
                <li key={phase.id}>
                  <button
                    type="button"
                    onClick={() => handlePhaseSelect(phase.id)}
                    className={`w-full rounded-lg border px-3 py-3 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${
                      phase.isCurrent
                        ? 'border-amber-500 bg-amber-50 text-amber-900 focus-visible:outline-amber-500 dark:border-amber-400 dark:bg-amber-500/10 dark:text-amber-100'
                        : 'border-transparent hover:border-slate-200 hover:bg-slate-100 focus-visible:outline-slate-400 dark:border-transparent dark:hover:border-slate-700 dark:hover:bg-slate-800/60 dark:text-slate-200'
                    } ${phase.isUpcoming && !phase.isCurrent ? 'opacity-60' : ''}`}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`flex h-9 w-9 items-center justify-center rounded-full border ${
                          phase.isCurrent
                            ? 'border-amber-500 bg-amber-100 text-amber-700 dark:border-amber-400 dark:bg-amber-400/20'
                            : 'border-slate-200 bg-white text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span
                            className={`font-semibold ${
                              phase.isCurrent
                                ? 'text-amber-900 dark:text-amber-200'
                                : 'text-slate-700 dark:text-slate-200'
                            }`}
                          >
                            {phase.title}
                          </span>
                          <span className="text-xs text-slate-400">#{phase.index + 1}</span>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400">{statusLabel}</p>
                      </div>
                      {phase.completed && <CheckCircle2 className="h-5 w-5 text-green-500" aria-hidden />}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="main-panel flex-1 overflow-y-auto p-6 bg-white dark:bg-slate-900/40">
          <div className="space-y-6">
            {currentPhaseMeta && (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
                    {currentPhaseMeta.title}
                  </h1>
                  <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                    {PHASE_DESCRIPTIONS[currentPhaseMeta.id]}
                  </p>
                </div>
                {currentPhaseMeta.completed && (
                  <span className="inline-flex items-center gap-1 self-start rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700 dark:bg-green-500/10 dark:text-green-300">
                    <CheckCircle2 className="h-4 w-4" /> Abgeschlossen
                  </span>
                )}
              </div>
            )}
            {isLoading && <p className="text-sm text-slate-500">Lade...</p>}
            {phaseContent}
          </div>
        </div>

        <aside className="w-80 flex-shrink-0 border-l border-slate-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800 p-4 overflow-y-auto">
          <h2 className="flex items-center gap-2 text-lg mb-2 text-slate-700 dark:text-slate-200">
            <History className="w-4 h-4" /> Backlog
          </h2>
          <ul className="space-y-2 text-sm">
            {backlog.map((t: any) => (
              <li
                key={t.id}
                className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-900"
              >
                <div className="text-slate-700 dark:text-slate-200">
                  <span className="text-amber-500 font-mono mr-2">{t.id}</span>
                  {t.description}
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
                    statusInfo[t.status]?.color ?? 'bg-slate-200 text-slate-700'
                  }`}
                >
                  {statusInfo[t.status]?.label ?? t.status}
                </span>
              </li>
            ))}
            {backlog.length === 0 && (
              <li className="italic text-slate-500 dark:text-slate-400">Queue is empty 🎉</li>
            )}
          </ul>

          <h2 className="flex items-center gap-2 text-lg mt-6 mb-2 text-slate-700 dark:text-slate-200">
            <Package className="w-4 h-4" /> Artifacts
          </h2>
          <ul className="space-y-2 text-sm">
            {artifacts.map((a) => (
              <li
                key={a.id}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-900"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-amber-500 font-mono text-xs">{a.task_id}</span>
                  {a.released && (
                    <span className="text-xs font-semibold text-green-600 dark:text-green-400">released</span>
                  )}
                </div>
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    downloadArtifactFile(a.id, a.repo_path?.split('/').pop() || a.id);
                  }}
                  className="mt-1 block truncate text-amber-500 hover:underline"
                >
                  {a.repo_path?.replace(/^[^/]+\//, '')}
                </a>
                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {a.media_type}, {a.created_at ? new Date(a.created_at).toLocaleString() : 'unbekannt'}
                </div>
              </li>
            ))}
            {artifacts.length === 0 && (
              <li className="italic text-slate-500 dark:text-slate-400">No artifacts yet</li>
            )}
          </ul>
        </aside>
      </div>
    </div>
  );
}
