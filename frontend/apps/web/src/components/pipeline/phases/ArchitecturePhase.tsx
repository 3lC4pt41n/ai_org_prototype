import PhaseArtifactAndChat, { type PreviousArtifactConfig } from '../../PhaseArtifactAndChat';
import type { PhaseViewContext } from '../types';

export function ArchitecturePhaseContent({
  archArtifact,
  architectureAwaitingApproval,
  onArchitectureApproved,
  prdArtifact,
  visionArtifact,
  selectedPurposeId,
  paused,
}: PhaseViewContext) {
  const previousArtifacts: PreviousArtifactConfig[] = [];
  if (prdArtifact?.id) {
    previousArtifacts.push({
      id: prdArtifact.id,
      title: 'Produktanforderung',
      phaseLabel: 'Phase: Produktanforderung',
    });
  }
  if (visionArtifact?.id) {
    previousArtifacts.push({
      id: visionArtifact.id,
      title: 'Projektvision',
      phaseLabel: 'Phase: Vision',
    });
  }

  return (
    <div className="space-y-6">
      <PhaseArtifactAndChat
        purposeId={selectedPurposeId}
        phaseKey="architecture"
        phaseTitle="Architektur"
        artifact={archArtifact}
        artifactName={archArtifact ? 'Architektur-Blueprint' : undefined}
        paused={paused}
        previousArtifacts={previousArtifacts}
        emptyMessage="Der Architekturentwurf ist noch in Arbeit. Sobald ein Artefakt vorliegt, wird der vollständige Inhalt hier angezeigt."
        onApproved={architectureAwaitingApproval ? onArchitectureApproved : undefined}
      />
    </div>
  );
}

export function ArchitecturePhaseSidebar({
  archArtifact,
  architectureAwaitingApproval,
}: PhaseViewContext) {
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
}
