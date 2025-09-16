import type { PhaseViewContext } from '../types';

export function ReleasePhaseContent({
  implementationCompleted,
  backlogEmpty,
  allArtifactsReleased,
  releaseCompleted,
  renderChatPanel,
}: PhaseViewContext) {
  const checklist = [
    { label: 'Aufgaben abgeschlossen', done: implementationCompleted },
    { label: 'Backlog leer', done: backlogEmpty },
    { label: 'Alle Artefakte freigegeben', done: allArtifactsReleased },
  ];

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Release vorbereiten</h3>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Koordiniere den Go-Live und stelle sicher, dass alle Freigaben vorliegen. Die Checkliste zeigt den aktuellen Status.
        </p>
        <ul className="mt-4 space-y-2 text-sm">
          {checklist.map((item) => (
            <li key={item.label} className="flex items-center justify-between gap-3">
              <span className="text-slate-700 dark:text-slate-200">{item.label}</span>
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                  item.done
                    ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-300'
                    : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                }`}
              >
                {item.done ? 'Erledigt' : 'Offen'}
              </span>
            </li>
          ))}
        </ul>
        {releaseCompleted ? (
          <p className="mt-4 text-sm text-green-600 dark:text-green-400">
            Alle Voraussetzungen erfüllt – das Release kann kommuniziert werden.
          </p>
        ) : (
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
            Markiere fehlende Schritte als abgeschlossen, um das Projekt erfolgreich zu beenden.
          </p>
        )}
      </section>
      {renderChatPanel({
        title: 'Release-Kommunikation',
        description:
          'Nutze den Chat für Abstimmungen zum Go-Live, zur Dokumentation oder für Lessons Learned nach Abschluss.',
      })}
    </div>
  );
}

export function ReleasePhaseSidebar({ releaseCompleted }: PhaseViewContext) {
  return (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Release-Status</h3>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        Stimme finale Kommunikation und Übergaben ab. Ein erfolgreicher Abschluss setzt freigegebene Artefakte und einen leeren Backlog voraus.
      </p>
      <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
        {releaseCompleted
          ? 'Alle Kriterien erfüllt – das Release kann kommuniziert werden.'
          : 'Noch offene Punkte vorhanden. Schließe Checkliste und Freigaben ab.'}
      </p>
    </section>
  );
}
