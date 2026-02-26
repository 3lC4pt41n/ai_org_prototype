import React, { useCallback } from 'react';
import ArtifactSection from './ArtifactSection';
import ChatPanelContainer from './pipeline/ChatPanelContainer';
import PhaseArtifactPreview, { type PhaseArtifactPreviewData } from './pipeline/PhaseArtifactPreview';
import type { ArtifactItem } from './pipeline/types';
import usePipelineStore from '../store/pipelineStore';

export type PreviousArtifactConfig = {
  id: string;
  title: string;
  phaseLabel?: string;
  artifact?: PhaseArtifactPreviewData;
};

type Props = {
  /** z.B. 'vision' | 'prd' | 'architecture' | 'architecture_review' | 'review' | 'release' */
  phaseKey: string;
  phaseTitle: string;
  purposeId: string | null;
  paused: boolean;

  /** Hauptartefakt der Phase – bevorzugt, damit ArtifactSection Versionen anzeigen kann */
  artifact?: ArtifactItem | null;
  /** Fallback: nur ID (wenn kein ArtifactItem vorliegt) */
  artifactId?: string | null;
  artifactName?: string;

  /** Vorgängerartefakte als schmale Read-only-Previews */
  previousArtifacts?: PreviousArtifactConfig[];
  /** Vorgänger komplett ausblenden (z. B. in PRD) */
  hidePrevious?: boolean;

  emptyMessage?: string;
  onApproved?: () => void;
};

export default function PhaseArtifactAndChat({
  purposeId,
  phaseKey,
  phaseTitle,
  artifact,
  artifactId,
  artifactName,
  previousArtifacts = [],
  hidePrevious,
  emptyMessage,
  onApproved,
  paused,
}: Props) {
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchBacklog = usePipelineStore((s) => s.fetchBacklog);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);
  const effectiveArtifact = artifact ?? (artifactId ? ({ id: artifactId } as ArtifactItem) : null);
  const effectiveArtifactId = effectiveArtifact?.id ?? null;
  const handleFeedbackSubmitted = useCallback(() => {
    const refreshes: Promise<unknown>[] = [fetchArtifacts(), fetchBacklog()];
    if (purposeId) {
      refreshes.push(fetchGraphAndStatus(purposeId));
    }
    void Promise.allSettled(refreshes);
  }, [fetchArtifacts, fetchBacklog, fetchGraphAndStatus, purposeId]);

  return (
    <div className="space-y-6">
      {effectiveArtifactId ? (
        <ArtifactSection
          title={artifactName ?? phaseTitle}
          artifact={effectiveArtifact!}
          statusIcon={null}
          showFeedback={!!onApproved}
          onApproved={onApproved}
        />
      ) : (
        <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
          <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">{phaseTitle}</h3>
          <p className="mt-2">
            {emptyMessage ?? 'Für diese Phase liegt noch kein Dokument vor.'}
          </p>
        </section>
      )}

      {!hidePrevious && previousArtifacts.length > 0 && (
        <div className="space-y-4">
          {previousArtifacts.map((p) => (
            <PhaseArtifactPreview
              key={p.id}
              title={p.title}
              phaseLabel={p.phaseLabel}
              artifact={p.artifact ?? ({ id: p.id } as PhaseArtifactPreviewData)}
              readOnly
            />
          ))}
        </div>
      )}

      <ChatPanelContainer
        title="Feedback & Fragen"
        description="Alle Rückmeldungen werden automatisch dieser Phase zugeordnet und im Artefakt gespeichert."
        purposeId={purposeId}
        paused={paused}
        artifactContext={
          effectiveArtifactId
            ? {
                artifactId: effectiveArtifactId,
                artifactTitle: artifactName ?? phaseTitle,
                phaseKey,
                phaseLabel: `Phase: ${phaseTitle}`,
                artifactReleased: !!artifact?.released,
              }
            : null
        }
        onArtifactApproved={onApproved}
        onFeedbackSubmitted={effectiveArtifactId ? handleFeedbackSubmitted : undefined}
      />
    </div>
  );
}
