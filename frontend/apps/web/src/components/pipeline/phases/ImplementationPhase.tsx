import GraphSection from '../../GraphSection';
import ChatPanelContainer from '../ChatPanelContainer';
import type { PhaseViewContext } from '../types';

const STATUS_ORDER = [
  'doing',
  'todo',
  'done',
  'blocked',
  'failed',
  'skipped',
  'budget_exceeded',
] as const;

export function ImplementationPhaseContent({
  graphNodes,
  graphEdges,
  graphStatusIcon,
  renderBacklogSection,
  selectedPurposeId,
  paused,
  chatFilterValue,
  setChatFilterValue,
}: PhaseViewContext) {
  return (
    <div className="space-y-6">
      {graphNodes.length > 0 ? (
        <GraphSection statusIcon={graphStatusIcon} nodes={graphNodes} edges={graphEdges} />
      ) : (
        <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300">
          <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Aufgaben werden vorbereitet</h3>
          <p className="mt-2">
            Der Task-Graph steht noch nicht zur Verfügung. Sobald Aufgaben generiert wurden, erscheint der Graph in dieser Phase.
          </p>
        </section>
      )}
      {renderBacklogSection()}
      <ChatPanelContainer
        title="Synchronisation mit AImar"
        description="Nutze den Chat, um Blocker, Testabdeckung oder Learnings zu dokumentieren. So bleibt das Delivery-Team auf Kurs."
        purposeId={selectedPurposeId}
        paused={paused}
        filterValue={chatFilterValue}
        onFilterValueChange={setChatFilterValue}
      />
    </div>
  );
}

export function ImplementationPhaseSidebar({
  statusInfo,
  statusCounters,
  hasTasks,
  allTasksDone,
  backlogEmpty,
}: PhaseViewContext) {
  const summaryEntries = STATUS_ORDER
    .map((status) => [status, statusCounters[status] ?? 0] as const)
    .filter(([, count]) => count > 0);

  return (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Task-Übersicht</h3>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        {hasTasks
          ? 'Behalte Fortschritt und Blocker im Blick, um die Umsetzung zu steuern.'
          : 'Sobald Aufgaben eingeplant sind, erscheinen Kennzahlen zu den Stati hier.'}
      </p>
      {summaryEntries.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-slate-600 dark:text-slate-300">
          {summaryEntries.map(([status, count]) => (
            <li key={status} className="flex items-center justify-between">
              <span>{statusInfo[status]?.label ?? status}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                  statusInfo[status]?.color ?? 'bg-slate-200 text-slate-700'
                }`}
              >
                {count}
              </span>
            </li>
          ))}
        </ul>
      )}
      {allTasksDone && backlogEmpty && (
        <p className="mt-3 text-xs text-green-600 dark:text-green-400">
          Alle Aufgaben abgeschlossen – bereite den Abschluss vor.
        </p>
      )}
    </section>
  );
}
