import PhaseArtifactAndChat from '../../PhaseArtifactAndChat';
import type { PhaseViewContext } from '../types';

export function VisionPhaseContent({
  selectedPurpose,
  selectedPurposeId,
  visionArtifact,
  visionAwaitingApproval,
  onVisionApproved,
  paused,
}: PhaseViewContext) {
  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">
          Projektvision schärfen
        </h3>
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
      <PhaseArtifactAndChat
        purposeId={selectedPurposeId}
        phaseKey="vision"
        phaseTitle="Vision"
        artifact={visionArtifact}
        artifactName={visionArtifact ? 'Projektvision' : undefined}
        paused={paused}
        emptyMessage="Die Vision ist noch in Arbeit. Sobald ein Artefakt erstellt wurde, erscheint es hier vollständig."
        onApproved={visionAwaitingApproval ? onVisionApproved : undefined}
      />
    </div>
  );
}

export function VisionPhaseSidebar({ visionArtifact, visionAwaitingApproval }: PhaseViewContext) {
  return (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Phase-Ziele</h3>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        {visionArtifact
          ? visionAwaitingApproval
            ? 'Vision liegt vor und wartet auf dein Feedback oder eine Freigabe.'
            : 'Vision freigegeben – die Produktanforderung nutzt dieses Briefing als Ausgangspunkt.'
          : 'Sammle Kontext, dokumentiere Annahmen und stelle sicher, dass alle Beteiligten das gleiche Zielbild teilen.'}
      </p>
      <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-slate-600 dark:text-slate-300">
        <li>Vision und Kontext im Chat dokumentieren</li>
        <li>Stakeholder, Zielgruppen und Erfolgskriterien festhalten</li>
        <li>Vision freigeben, um die Produktanforderung zu starten</li>
      </ul>
      {visionArtifact?.created_at && (
        <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
          Letzte Aktualisierung: {new Date(visionArtifact.created_at).toLocaleString()}
        </p>
      )}
    </section>
  );
}
