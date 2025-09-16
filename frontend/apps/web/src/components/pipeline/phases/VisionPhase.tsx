import type { PhaseViewContext } from '../types';

export function VisionPhaseContent({
  selectedPurpose,
  renderChatPanel,
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
      {renderChatPanel({
        title: 'Vision mit AImar ausarbeiten',
        description:
          'Nutze den Dialog, um Stakeholder, Zielgruppen und Erfolgskriterien zu dokumentieren. Diese Inhalte dienen als Briefing für die nachfolgenden Phasen.',
      })}
    </div>
  );
}

export function VisionPhaseSidebar() {
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
}
