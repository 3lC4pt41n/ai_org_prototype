import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  History,
  Package,
  Lightbulb,
  FileText,
  CircuitBoard,
  Hammer,
  ClipboardCheck,
  CheckCircle2,
  Target,
  ShieldCheck,
  Rocket,
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

const PIPELINE_PHASES = [
  { id: 'purpose', title: 'Projektziel', icon: Target },
  { id: 'vision', title: 'Vision', icon: Lightbulb },
  { id: 'prd', title: 'Produktanforderung', icon: FileText },
  { id: 'architecture', title: 'Architektur', icon: CircuitBoard },
  { id: 'architecture_review', title: 'Architektur & Domain Review', icon: ShieldCheck },
  { id: 'implementation', title: 'Implementierung', icon: Hammer },
  { id: 'review', title: 'Review', icon: ClipboardCheck },
  { id: 'release', title: 'Release', icon: Rocket },
] as const;

type PhaseId = (typeof PIPELINE_PHASES)[number]['id'];

interface PhaseMeta {
  id: PhaseId;
  title: string;
  icon: LucideIcon;
  completed: boolean;
  index: number;
  isCurrent: boolean;
  isUpcoming: boolean;
}

const PHASE_ORDER: PhaseId[] = PIPELINE_PHASES.map((phase) => phase.id);

const PHASE_DESCRIPTIONS: Record<PhaseId, string> = {
  purpose:
    'Lege das Projektziel fest, indem du einen Purpose auswählst oder erstellst. Dies bestimmt den weiteren Verlauf der Pipeline.',
  vision:
    'Schärfe Vision und Kontext des Projekts. Dokumentiere Rahmenbedingungen, Zielgruppen und Erfolgsfaktoren.',
  prd: 'Erarbeite die Produktanforderungen und stelle sicher, dass alle Stakeholder den gleichen Stand teilen.',
  architecture:
    'Gestalte das technische Fundament. Das Architektur-Blueprint bildet die Basis für eine belastbare Implementierung.',
  architecture_review:
    'Überprüfe Architekturentscheidungen gemeinsam mit Domain-Expert*innen und gib das Review-Dokument frei.',
  implementation:
    'Arbeite die Aufgaben aus dem Task-Graph ab und kollaboriere mit dem Team entlang der Pipeline.',
  review:
    'Koordiniere finale Abstimmungen, teste Ergebnisse und bereite die Freigabe vor.',
  release:
    'Schließe das Projekt ab, indem du alle Artefakte freigibst und das Release kommunizierst.',
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
  const architectureReviewArtifact = artifacts.find((a) =>
    a.repo_path?.toLowerCase().includes('architecture_domain_review'),
  );
  const architectureArtifactId = archArtifact?.id ?? null;
  const architectureReviewArtifactId = architectureReviewArtifact?.id ?? null;

  const prdAwaitingApproval = !!prdArtifact && !prdArtifact.released;
  const architectureAwaitingApproval = !!archArtifact && !archArtifact.released;
  const architectureReviewAwaitingApproval =
    !!architectureReviewArtifact && !architectureReviewArtifact.released;

  const prdStatusIcon = prdArtifact ? (prdAwaitingApproval ? '🕓' : '✅') : '🕓';
  const archStatusIcon = archArtifact ? (architectureAwaitingApproval ? '🕓' : '✅') : '🕓';
  const architectureReviewStatusIcon = architectureReviewArtifact
    ? architectureReviewAwaitingApproval
      ? '🕓'
      : '✅'
    : '🕓';
  const graphStatusIcon = paused ? '🕓' : '✅';

  const tasksStatusValues = Object.values(tasksStatus ?? {});
  const hasTasks = tasksStatusValues.length > 0;
  const allTasksDone = hasTasks && tasksStatusValues.every((status) => status === 'done');
  const backlogEmpty = backlog.length === 0;
  const releasedArtifacts = artifacts.filter((a) => a.released);
  const allArtifactsReleased = artifacts.length > 0 && releasedArtifacts.length === artifacts.length;
  const selectedPurpose = purposes.find((p) => p.id === selectedPurposeId) || null;

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

  const statusCounters = useMemo(
    () =>
      tasksStatusValues.reduce<Record<string, number>>((acc, status) => {
        acc[status] = (acc[status] ?? 0) + 1;
        return acc;
      }, {}),
    [tasksStatusValues],
  );

  const purposeCompleted = Boolean(selectedPurposeId);
  const visionCompleted = Boolean(prdArtifact);
  const prdCompleted = Boolean(prdArtifact?.released);
  const architectureCompleted = Boolean(archArtifact?.released);
  const architectureReviewCompleted = Boolean(architectureReviewArtifact?.released);
  const implementationCompleted = allTasksDone;
  const reviewCompleted = implementationCompleted && backlogEmpty;
  const releaseCompleted = reviewCompleted && allArtifactsReleased;

  const phaseCompletion: Record<PhaseId, boolean> = {
    purpose: purposeCompleted,
    vision: visionCompleted,
    prd: prdCompleted,
    architecture: architectureCompleted,
    architecture_review: architectureReviewCompleted,
    implementation: implementationCompleted,
    review: reviewCompleted,
    release: releaseCompleted,
  };

  const recommendedPhase = useMemo<PhaseId>(() => {
    if (!purposeCompleted) return 'purpose';
    if (!visionCompleted) return 'vision';
    if (!prdCompleted) return 'prd';
    if (!architectureCompleted) return 'architecture';
    if (!architectureReviewCompleted) return 'architecture_review';
    if (!implementationCompleted) return 'implementation';
    if (!reviewCompleted) return 'review';
    if (!releaseCompleted) return 'release';
    return 'release';
  }, [
    purposeCompleted,
    visionCompleted,
    prdCompleted,
    architectureCompleted,
    architectureReviewCompleted,
    implementationCompleted,
    reviewCompleted,
    releaseCompleted,
  ]);

  const [currentPhase, setCurrentPhaseInternal] = useState<PhaseId>(recommendedPhase);
  const [chatFilterValue, setChatFilterValue] = useState<string>('all');
  const userSelectedPhaseRef = useRef(false);

  const applyChatFilterForPhase = useCallback(
    (phase: PhaseId, options?: { redirectArtifactId?: string }) => {
      if (phase === 'architecture' || phase === 'architecture_review') {
        if (options?.redirectArtifactId) {
          setChatFilterValue(options.redirectArtifactId);
          return;
        }
        if (phase === 'architecture' && architectureArtifactId) {
          setChatFilterValue(architectureArtifactId);
          return;
        }
        if (phase === 'architecture_review' && architectureReviewArtifactId) {
          setChatFilterValue(architectureReviewArtifactId);
          return;
        }
      }
      setChatFilterValue('all');
    },
    [architectureArtifactId, architectureReviewArtifactId],
  );

  useEffect(() => {
    setCurrentPhaseInternal((prev) => {
      const prevIndex = PHASE_ORDER.indexOf(prev);
      const recommendedIndex = PHASE_ORDER.indexOf(recommendedPhase);
      if (!userSelectedPhaseRef.current || recommendedIndex > prevIndex) {
        if (recommendedIndex !== prevIndex) {
          userSelectedPhaseRef.current = false;
          applyChatFilterForPhase(recommendedPhase);
        }
        return recommendedPhase;
      }
      return prev;
    });
  }, [recommendedPhase, applyChatFilterForPhase]);

  const setPhase = useCallback(
    (phase: PhaseId, options?: { redirectArtifactId?: string }) => {
      userSelectedPhaseRef.current = true;
      setCurrentPhaseInternal(phase);
      applyChatFilterForPhase(phase, options);
    },
    [applyChatFilterForPhase],
  );

  const handlePhaseSelect = (phase: PhaseId) => {
    setPhase(phase);
  };

  const getNextPhase = (phase: PhaseId): PhaseId | null => {
    const index = PHASE_ORDER.indexOf(phase);
    if (index === -1 || index >= PHASE_ORDER.length - 1) {
      return null;
    }
    return PHASE_ORDER[index + 1];
  };

  const handleArtifactApproved = (
    phase: PhaseId,
    info?: { redirectArtifactId?: string; redirectArtifactUrl?: string },
  ) => {
    const nextPhase = getNextPhase(phase);
    if (!nextPhase) return;
    setPhase(nextPhase, { redirectArtifactId: info?.redirectArtifactId });
  };

  useEffect(() => {
    setChatFilterValue('all');
  }, [selectedPurposeId]);

  const phases = useMemo<PhaseMeta[]>(() => {
    let previousCompleted = true;
    return PIPELINE_PHASES.map((phase, index) => {
      const completed = phaseCompletion[phase.id];
      const isCurrent = currentPhase === phase.id;
      const isUpcoming = !completed && !previousCompleted && !isCurrent;
      if (!completed) {
        previousCompleted = false;
      }
      return {
        id: phase.id,
        title: phase.title,
        icon: phase.icon,
        completed,
        index,
        isCurrent,
        isUpcoming,
      } satisfies PhaseMeta;
    });
  }, [
    currentPhase,
    purposeCompleted,
    visionCompleted,
    prdCompleted,
    architectureCompleted,
    architectureReviewCompleted,
    implementationCompleted,
    reviewCompleted,
    releaseCompleted,
  ]);

  const currentPhaseMeta = phases.find((phase) => phase.id === currentPhase) ?? phases[0];

  const getPhaseStatusLabel = (phase: PhaseMeta) => {
    if (phase.completed) return 'Abgeschlossen';
    if (phase.isCurrent) return 'Aktive Phase';
    if (phase.isUpcoming) return 'Geplant';
    return 'Bereit';
  };

  const renderChatPanel = ({
    title,
    description,
    placeholderTitle,
    placeholderDescription,
    className = '',
  }: {
    title: string;
    description?: string;
    placeholderTitle?: string;
    placeholderDescription?: string;
    className?: string;
  }) => {
    if (!selectedPurposeId) {
      return (
        <section
          className={`rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300 ${className}`.trim()}
        >
          <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">
            {placeholderTitle ?? 'Kein Purpose ausgewählt'}
          </h3>
          <p className="mt-2">
            {placeholderDescription ??
              'Wähle im Kopfbereich einen Purpose aus, um Artefakte zu erstellen und mit dem KI-Produkt Owner zu interagieren.'}
          </p>
        </section>
      );
    }

    return (
      <section
        className={`rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 sm:p-6 shadow-sm ${className}`.trim()}
      >
        <div className="flex flex-col gap-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">{title}</h3>
            {description && <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{description}</p>}
          </div>
          <AImarChatPanel
            purposeId={selectedPurposeId}
            paused={paused}
            filterValue={chatFilterValue}
            onFilterValueChange={setChatFilterValue}
          />
        </div>
      </section>
    );
  };

  const renderBacklogSection = () => (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-700 dark:text-slate-200">
          <History className="h-4 w-4 text-slate-500 dark:text-slate-400" /> Aufgaben-Backlog
        </h3>
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
          {backlog.length > 0 ? `${backlog.length} offene Einträge` : 'keine offenen Aufgaben'}
        </span>
      </div>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        {backlog.length > 0
          ? 'Überwache den Status der Aufgaben und gib bei Bedarf Rückmeldung, um Blocker schnell zu erkennen.'
          : 'Der Backlog ist aktuell leer – sobald neue Aufgaben geplant werden, erscheinen sie hier.'}
      </p>
      <ul className="mt-4 space-y-2 text-sm">
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
          <li className="italic text-slate-500 dark:text-slate-400">Keine offenen Aufgaben 🎉</li>
        )}
      </ul>
    </section>
  );

  const phaseContent = (() => {
    switch (currentPhase) {
      case 'purpose':
        return (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Projektziel festlegen</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                Nutze den Selektor im Kopfbereich, um ein Projektziel zu aktivieren oder neu anzulegen. Damit bestimmst du,
                welche Artefakte und Aufgaben in den folgenden Schritten erzeugt werden.
              </p>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                {selectedPurpose
                  ? `Aktueller Purpose: ${selectedPurpose.name}`
                  : 'Noch kein Purpose ausgewählt. Wähle einen Purpose aus, um den Ablauf zu starten.'}
              </p>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Tipp: Halte ergänzende Rahmenbedingungen direkt im Chat fest, sobald du zur Vision-Phase wechselst.
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
                  Noch keine Purposes vorhanden. Lege ein Projektziel an, um mit der Pipeline zu starten.
                </p>
              )}
            </section>
          </div>
        );
      case 'vision':
        return (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Projektvision schärfen</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                Beschreibe Zielbild, Nutzen und Grenzen deiner Initiative. Die erarbeiteten Leitplanken fließen in die
                Produktanforderung ein.
              </p>
              {selectedPurpose && (
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                  Aktueller Purpose: <span className="font-medium">{selectedPurpose.name}</span>
                </p>
              )}
            </section>
            {renderChatPanel({
              title: 'Vision mit AImar ausarbeiten',
              description:
                'Nutze den Dialog, um Stakeholder, Zielgruppen und Erfolgskriterien zu dokumentieren. Diese Inhalte dienen als Briefing für die nachfolgenden Phasen.',
            })}
          </div>
        );
      case 'prd':
        return (
          <div className="space-y-6">
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
              {renderChatPanel({
                title: 'Produkt-Owner-Dialog',
                description:
                  'Verfeinere Anforderungen, beantworte Rückfragen und gib zusätzliche Kontexte, damit die Produktanforderung vollständig wird.',
                placeholderTitle: 'AImar-Dialog noch nicht verfügbar',
                placeholderDescription:
                  'Wähle einen Purpose aus, um mit dem KI-Produkt Owner zu sprechen und die Produktanforderung vorzubereiten.',
                className: 'h-full',
              })}
              {prdArtifact ? (
                <ArtifactSection
                  title="Produktanforderung"
                  artifact={prdArtifact}
                  statusIcon={prdStatusIcon}
                  showFeedback={prdAwaitingApproval}
                  onApproved={(info) => handleArtifactApproved('prd', info)}
                />
              ) : (
                <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
                  <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Produktanforderung in Erstellung</h3>
                  <p className="mt-2">
                    Sobald die Produktanforderung generiert wurde, erscheint sie hier zur Durchsicht und Kommentierung.
                  </p>
                  <p className="mt-2">
                    Nutze den Dialog mit AImar, um zusätzliche Anforderungen zu beschreiben oder Unklarheiten zu adressieren.
                  </p>
                </section>
              )}
            </div>
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
                showFeedback={architectureAwaitingApproval}
                onApproved={(info) => handleArtifactApproved('architecture', info)}
              />
            ) : (
              <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
                <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Architektur in Vorbereitung</h3>
                <p className="mt-2">
                  Das Architektur-Blueprint ist noch nicht verfügbar. Sobald die Modellierung abgeschlossen ist, kannst du hier Feedback geben.
                </p>
                {prdArtifact && (
                  <p className="mt-2">
                    Die Produktanforderung liegt bereits vor und dient als Grundlage für die Architekturphase.
                  </p>
                )}
              </section>
            )}
            {renderChatPanel({
              title: 'Rückfragen zur Architektur',
              description:
                'Besprich technische Annahmen oder kläre Änderungswünsche. Der Chat bleibt verfügbar, auch wenn der Fokus auf dem Blueprint liegt.',
            })}
          </div>
        );
      case 'architecture_review':
        return (
          <div className="space-y-6">
            {architectureReviewArtifact ? (
              <ArtifactSection
                title="Architektur & Domain Review"
                artifact={architectureReviewArtifact}
                statusIcon={architectureReviewStatusIcon}
                showFeedback={architectureReviewAwaitingApproval}
                onApproved={(info) => handleArtifactApproved('architecture_review', info)}
              />
            ) : (
              <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
                <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Review in Vorbereitung</h3>
                <p className="mt-2">
                  Der Review-Bericht wird erstellt. Sobald die Domain-Expert*innen ihre Einschätzung abgegeben haben, erscheint das Dokument hier.
                </p>
                {archArtifact && (
                  <p className="mt-2">
                    Der Architektur-Entwurf wurde bereits erstellt und bildet die Grundlage für dieses Review.
                  </p>
                )}
              </section>
            )}
            {renderChatPanel({
              title: 'Abstimmung mit Reviewer*innen',
              description:
                'Dokumentiere Rückfragen, Freigaben oder benötigte Anpassungen, bevor die Implementierung weitergeht.',
            })}
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
                  Der Task-Graph steht noch nicht zur Verfügung. Sobald Aufgaben generiert wurden, erscheint der Graph in dieser Phase.
                </p>
              </section>
            )}
            {renderBacklogSection()}
            {renderChatPanel({
              title: 'Synchronisation mit AImar',
              description:
                'Nutze den Chat, um Blocker, Testabdeckung oder Learnings zu dokumentieren. So bleibt das Delivery-Team auf Kurs.',
            })}
          </div>
        );
      case 'review':
        return (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Review-Übersicht</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                Prüfe die erstellten Artefakte, sammle Feedback aus dem Team und entscheide, welche Ergebnisse für das Release bereit sind.
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
            {renderChatPanel({
              title: 'Abschluss & Feedback',
              description: 'Halte finale Entscheidungen fest oder melde letzte Änderungswünsche an das Team zurück.',
            })}
          </div>
        );
      case 'release': {
        const checklist = [
          { label: 'Aufgaben abgeschlossen', done: implementationCompleted },
          { label: 'Backlog leer', done: backlogEmpty },
          { label: 'Alle Artefakte freigegeben', done: allArtifactsReleased },
        ];
        return (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Release vorbereiten</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                Koordiniere den Go-Live und stelle sicher, dass alle Freigaben vorliegen. Die Checkliste zeigt den aktuellen Status.
              </p>
              <ul className="mt-4 space-y-2 text-sm">
                {checklist.map((item) => (
                  <li key={item.label} className="flex items-center justify-between gap-3">
                    <span className="text-slate-700 dark:text-slate-200">{item.label}</span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                        item.done
                          ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-300'
                          : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                      }`}
                    >
                      {item.done ? 'Erledigt' : 'Offen'}
                    </span>
                  </li>
                ))}
              </ul>
              {releaseCompleted ? (
                <p className="mt-4 text-sm text-green-600 dark:text-green-400">
                  Alle Voraussetzungen erfüllt – das Release kann kommuniziert werden.
                </p>
              ) : (
                <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
                  Markiere fehlende Schritte als abgeschlossen, um das Projekt erfolgreich zu beenden.
                </p>
              )}
            </section>
            {renderChatPanel({
              title: 'Release-Kommunikation',
              description:
                'Nutze den Chat für Abstimmungen zum Go-Live, zur Dokumentation oder für Lessons Learned nach Abschluss.',
            })}
          </div>
        );
      }
      default:
        return null;
    }
  })();

  const phaseSidebarContent = (() => {
    switch (currentPhase) {
      case 'purpose':
        return (
          <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Phase-Ziele</h3>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Aktiviere das passende Projektziel und stimme dich mit Stakeholdern ab, bevor du in die Vision einsteigst.
            </p>
            <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-slate-600 dark:text-slate-300">
              <li>Purpose auswählen oder neu anlegen</li>
              <li>Verantwortlichkeiten für den nächsten Schritt klären</li>
            </ul>
          </section>
        );
      case 'vision':
        return (
          <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Phase-Ziele</h3>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Sammle Kontext, dokumentiere Annahmen und stelle sicher, dass alle Beteiligten das gleiche Zielbild teilen.
            </p>
            <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-slate-600 dark:text-slate-300">
              <li>Vision und Kontext im Chat dokumentieren</li>
              <li>Offene Fragen für die Produktanforderung sammeln</li>
            </ul>
          </section>
        );
      case 'prd':
        return (
          <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Produktanforderung</h3>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {prdArtifact
                ? prdAwaitingApproval
                  ? 'Die Produktanforderung wartet auf dein Feedback oder eine Freigabe.'
                  : 'Produktanforderung freigegeben – die Architektur kann weiterarbeiten.'
                : 'Die Produktanforderung wird erstellt. Du wirst informiert, sobald ein Entwurf vorliegt.'}
            </p>
            {prdArtifact?.created_at && (
              <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
                Letzte Aktualisierung: {new Date(prdArtifact.created_at).toLocaleString()}
              </p>
            )}
          </section>
        );
      case 'architecture':
        return (
          <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Architektur-Status</h3>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {archArtifact
                ? architectureAwaitingApproval
                  ? 'Der Architektur-Entwurf wartet auf dein Feedback oder eine Freigabe.'
                  : 'Architektur bestätigt – das Domain-Review kann erfolgen.'
                : 'Der Blueprint wird vorbereitet. Prüfe später erneut die Ergebnisse.'}
            </p>
            {archArtifact?.created_at && (
              <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
                Vorschlag erzeugt am {new Date(archArtifact.created_at).toLocaleString()}
              </p>
            )}
          </section>
        );
      case 'architecture_review':
        return (
          <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Domain Review</h3>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {architectureReviewArtifact
                ? architectureReviewAwaitingApproval
                  ? 'Das Review-Dokument wartet auf deine Rückmeldung oder Freigabe.'
                  : 'Review bestätigt – der Weg zur Implementierung ist frei.'
                : 'Das Review wird vorbereitet. Du erhältst eine Benachrichtigung, sobald der Entwurf bereitsteht.'}
            </p>
            {architectureReviewArtifact?.created_at && (
              <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
                Review erstellt am {new Date(architectureReviewArtifact.created_at).toLocaleString()}
              </p>
            )}
          </section>
        );
      case 'implementation': {
        const statusOrder: Array<keyof typeof statusInfo> = [
          'doing',
          'todo',
          'done',
          'blocked',
          'failed',
          'skipped',
          'budget_exceeded',
        ];
        const summaryEntries = statusOrder
          .map((status) => [status, statusCounters[status] ?? 0] as const)
          .filter(([, count]) => count > 0);
        return (
          <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Task-Übersicht</h3>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {hasTasks
                ? 'Behalte Fortschritt und Blocker im Blick, um die Umsetzung zu steuern.'
                : 'Sobald Aufgaben eingeplant sind, erscheinen Kennzahlen zu den Stati hier.'}
            </p>
            {summaryEntries.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs text-slate-600 dark:text-slate-300">
                {summaryEntries.map(([status, count]) => (
                  <li key={status} className="flex items-center justify-between">
                    <span>{statusInfo[status]?.label ?? status}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                        statusInfo[status]?.color ?? 'bg-slate-200 text-slate-700'
                      }`}
                    >
                      {count}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {allTasksDone && backlogEmpty && (
              <p className="mt-3 text-xs text-green-600 dark:text-green-400">
                Alle Aufgaben abgeschlossen – bereite den Abschluss vor.
              </p>
            )}
          </section>
        );
      }
      case 'review':
        return (
          <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Review-Fokus</h3>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Richte den Blick auf verbleibende Feedback-Schleifen und plane Freigaben für das Release ein.
            </p>
            <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
              {artifacts.length > 0
                ? `${releasedArtifacts.length}/${artifacts.length} Artefakte freigegeben.`
                : 'Noch keine Artefakte erzeugt.'}
            </p>
            {releasedArtifacts.length < artifacts.length && artifacts.length > 0 && (
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Plane Freigaben ein, damit der Release-Schritt nahtlos folgen kann.
              </p>
            )}
          </section>
        );
      case 'release':
        return (
          <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Release-Status</h3>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Stimme finale Kommunikation und Übergaben ab. Ein erfolgreicher Abschluss setzt freigegebene Artefakte und einen leeren Backlog voraus.
            </p>
            <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
              {releaseCompleted
                ? 'Alle Kriterien erfüllt – das Release kann kommuniziert werden.'
                : 'Noch offene Punkte vorhanden. Schließe Checkliste und Freigaben ab.'}
            </p>
          </section>
        );
      default:
        return null;
    }
  })();

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
          {phaseSidebarContent && <div className="mb-6">{phaseSidebarContent}</div>}

          <h2 className="flex items-center gap-2 text-lg mb-2 text-slate-700 dark:text-slate-200">
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
