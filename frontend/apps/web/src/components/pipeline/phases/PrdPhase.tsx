import ArtifactSection from '../../ArtifactSection';
import type { PhaseViewContext } from '../types';

export function PrdPhaseContent({
  prdArtifact,
  prdStatusIcon,
  prdAwaitingApproval,
  onPrdApproved,
  renderChatPanel,
}: PhaseViewContext) {
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
            onApproved={onPrdApproved}
          />
        ) : (
          <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
            <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">
              Produktanforderung in Erstellung
            </h3>
            <p className="mt-2">
              Sobald die Produktanforderung generiert wurde, erscheint sie hier zur Durchsicht und Kommentierung.
            </p>
          </section>
        )}
      </div>
      {renderChatPanel({
        title: 'Abstimmung für Folgephasen',
        description:
          'Halte zusätzliche Annahmen oder Änderungswünsche fest. Sie fließen unmittelbar in die weiteren Phasen ein.',
      })}
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
