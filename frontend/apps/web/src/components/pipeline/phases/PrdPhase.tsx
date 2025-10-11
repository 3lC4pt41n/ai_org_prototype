import PhaseArtifactAndChat, { type PreviousArtifactConfig } from '../../PhaseArtifactAndChat';
import type { PhaseViewContext } from '../types';

export function PrdPhaseContent({
  prdArtifact,
  onPrdApproved,
  selectedPurposeId,
  paused,
  visionArtifact,
}: PhaseViewContext) {
  const previousArtifacts: PreviousArtifactConfig[] = [];
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
        phaseKey="prd"
        phaseTitle="Produktanforderung"
        artifactId={prdArtifact?.id}
        artifactName={prdArtifact ? 'Produktanforderung' : undefined}
        paused={paused}
        previousArtifacts={previousArtifacts}
        emptyMessage="Die Produktanforderung ist noch nicht verfügbar. Sobald AImar das Artefakt erstellt hat, erscheint es hier vollständig."
        onApproved={() => onPrdApproved?.({})}
      />
    </div>
  );
}

export function PrdPhaseSidebar({ prdArtifact, prdAwaitingApproval }: PhaseViewContext) {
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
}
