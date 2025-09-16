import ArtifactSection from '../../ArtifactSection';
import type { PhaseViewContext } from '../types';

export function ArchitecturePhaseContent({
  archArtifact,
  archStatusIcon,
  architectureAwaitingApproval,
  onArchitectureApproved,
  prdArtifact,
  renderChatPanel,
}: PhaseViewContext) {
  return (
    <div className="space-y-6">
      {archArtifact ? (
        <ArtifactSection
          title="Architektur"
          artifact={archArtifact}
          statusIcon={archStatusIcon}
          showFeedback={architectureAwaitingApproval}
          onApproved={onArchitectureApproved}
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
