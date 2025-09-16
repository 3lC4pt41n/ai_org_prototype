import type { PhaseViewContext } from '../types';

export function ReviewPhaseContent({ artifacts, renderChatPanel }: PhaseViewContext) {
  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Review-Übersicht</h3>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Prüfe die erstellten Artefakte, sammle Feedback aus dem Team und entscheide, welche Ergebnisse für das Release bereit sind.
        </p>
        <ul className="mt-4 space-y-2 text-sm">
          {artifacts.length > 0 ? (
            artifacts.map((artifact) => {
              const fileName = artifact.repo_path?.split('/').pop() || artifact.id;
              return (
                <li key={artifact.id} className="flex items-center justify-between">
                  <span className="truncate pr-2 text-slate-700 dark:text-slate-200">{fileName}</span>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                      artifact.released
                        ? 'bg-green-100 text-green-700'
                        : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                    }`}
                  >
                    {artifact.released ? 'Freigegeben' : 'In Prüfung'}
                  </span>
                </li>
              );
            })
          ) : (
            <li className="text-slate-600 dark:text-slate-300">Noch keine Artefakte vorhanden.</li>
          )}
        </ul>
      </section>
      {renderChatPanel({
        title: 'Abschluss & Feedback',
        description: 'Halte finale Entscheidungen fest oder melde letzte Änderungswünsche an das Team zurück.',
      })}
    </div>
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
