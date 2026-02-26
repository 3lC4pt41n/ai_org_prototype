import PhaseArtifactAndChat, { type PreviousArtifactConfig } from '../../PhaseArtifactAndChat';
import type { PhaseViewContext } from '../types';

export function ArchitectureReviewPhaseContent(ctx: PhaseViewContext) {
  const {
    archArtifact,
    architectureReviewArtifact,
    architectureReviewAwaitingApproval,
    onArchitectureReviewApproved,
    selectedPurposeId,
    paused,
  } = ctx;
  const previousArtifacts: PreviousArtifactConfig[] = [];
  if (archArtifact?.id) {
    previousArtifacts.push({
      id: archArtifact.id,
      title: 'Architektur-Blueprint',
      phaseLabel: 'Phase: Architektur',
      artifact: {
        id: archArtifact.id,
        path: archArtifact.repo_path,
        media_type: archArtifact.media_type,
        created_at: archArtifact.created_at,
        released: archArtifact.released,
        url: archArtifact.url,
      },
    });
  }
  return (
    <PhaseArtifactAndChat
      purposeId={selectedPurposeId}
      phaseKey="architecture_review"
      phaseTitle="Architektur-Review"
      artifact={architectureReviewArtifact}
      artifactName={architectureReviewArtifact ? 'Architektur & Domain Review' : undefined}
      paused={paused}
      previousArtifacts={previousArtifacts}
      emptyMessage="Der Review-Bericht wird vorbereitet. Sobald die Einschätzung vorliegt, erscheint das Dokument hier."
      onApproved={architectureReviewAwaitingApproval ? onArchitectureReviewApproved : undefined}
    />
  );
}

export function ArchitectureReviewPhaseSidebar({
  architectureReviewArtifact,
  architectureReviewAwaitingApproval,
}: PhaseViewContext) {
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
}
