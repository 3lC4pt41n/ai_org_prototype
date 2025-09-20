import ArtifactSection from '../../ArtifactSection';
import ChatPanelContainer from '../ChatPanelContainer';
import type { PhaseViewContext } from '../types';

export function ArchitectureReviewPhaseContent({
  architectureReviewArtifact,
  architectureReviewStatusIcon,
  architectureReviewAwaitingApproval,
  onArchitectureReviewApproved,
  archArtifact,
  selectedPurposeId,
  paused,
  chatFilterValue,
  setChatFilterValue,
}: PhaseViewContext) {
  return (
    <div className="space-y-6">
      {architectureReviewArtifact ? (
        <ArtifactSection
          title="Architektur & Domain Review"
          artifact={architectureReviewArtifact}
          statusIcon={architectureReviewStatusIcon}
          showFeedback={architectureReviewAwaitingApproval}
          onApproved={onArchitectureReviewApproved}
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
      <ChatPanelContainer
        title="Abstimmung mit Reviewer*innen"
        description="Dokumentiere Rückfragen, Freigaben oder benötigte Anpassungen, bevor die Implementierung weitergeht."
        purposeId={selectedPurposeId}
        paused={paused}
        filterValue={chatFilterValue}
        onFilterValueChange={setChatFilterValue}
      />
    </div>
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
