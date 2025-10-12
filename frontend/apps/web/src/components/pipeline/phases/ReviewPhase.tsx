import PhaseArtifactAndChat, { type PreviousArtifactConfig } from '../../PhaseArtifactAndChat';
import type { PhaseViewContext } from '../types';

export function ReviewPhaseContent(ctx: PhaseViewContext) {
  const { archArtifact, architectureReviewArtifact, selectedPurposeId, paused } = ctx;
  const previousArtifacts: PreviousArtifactConfig[] = [];
  if (architectureReviewArtifact?.id) {
    previousArtifacts.push({
      id: architectureReviewArtifact.id,
      title: 'Architektur & Domain Review',
      phaseLabel: 'Phase: Architektur-Review',
    });
  }
  return (
    <PhaseArtifactAndChat
      purposeId={selectedPurposeId}
      phaseKey="review"
      phaseTitle="Review"
      artifact={archArtifact}
      artifactName={archArtifact ? 'Architektur-Blueprint' : undefined}
      paused={paused}
      previousArtifacts={previousArtifacts}
      emptyMessage="Noch keine Artefakte für das Review vorhanden."
    />
  );
}

export function ReviewPhaseSidebar({ artifacts, releasedArtifacts }: PhaseViewContext) {
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
}
