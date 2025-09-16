import type { PhaseViewContext } from '../types';

export function PurposePhaseContent({
  purposes,
  selectedPurpose,
  selectedPurposeId,
}: PhaseViewContext) {
  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">
          Projektziel festlegen
        </h3>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Nutze den Selektor im Kopfbereich, um ein Projektziel zu aktivieren oder neu anzulegen. Damit bestimmst du,
          welche Artefakte und Aufgaben in den folgenden Schritten erzeugt werden.
        </p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          {selectedPurpose
            ? `Aktueller Purpose: ${selectedPurpose.name}`
            : 'Noch kein Purpose ausgewählt. Wähle einen Purpose aus, um den Ablauf zu starten.'}
        </p>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Tipp: Halte ergänzende Rahmenbedingungen direkt im Chat fest, sobald du zur Vision-Phase wechselst.
        </p>
      </section>
      <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <h3 className="text-base font-semibold text-slate-700 dark:text-slate-200">Verfügbare Purposes</h3>
        {purposes.length > 0 ? (
          <ul className="mt-4 space-y-2 text-sm">
            {purposes.map((purpose) => (
              <li
                key={purpose.id}
                className={`flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 ${
                  purpose.id === selectedPurposeId
                    ? 'bg-amber-50 text-amber-900 dark:bg-amber-500/10'
                    : 'bg-slate-50 text-slate-700 dark:bg-slate-800/60 dark:text-slate-200'
                }`}
              >
                <span className="font-medium">{purpose.name}</span>
                {purpose.id === selectedPurposeId ? (
                  <span className="text-xs font-semibold text-amber-600">Aktiv</span>
                ) : (
                  <span className="text-xs text-slate-500 dark:text-slate-400">Auswahl möglich</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            Noch keine Purposes vorhanden. Lege ein Projektziel an, um mit der Pipeline zu starten.
          </p>
        )}
      </section>
    </div>
  );
}

export function PurposePhaseSidebar() {
  return (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Phase-Ziele</h3>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        Aktiviere das passende Projektziel und stimme dich mit Stakeholdern ab, bevor du in die Vision einsteigst.
      </p>
      <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-slate-600 dark:text-slate-300">
        <li>Purpose auswählen oder neu anlegen</li>
        <li>Verantwortlichkeiten für den nächsten Schritt klären</li>
      </ul>
    </section>
  );
}
