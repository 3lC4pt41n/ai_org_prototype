import React, { useState } from 'react';
import { toast } from 'react-hot-toast';
import usePipelineStore from '../store/pipelineStore';

export default function PurposeSelector() {
  const {
    purposes,
    selectedPurposeId,
    setSelectedPurpose,
    pausePurpose,
    startPurpose,
    updatePurposeMode,
  } = usePipelineStore();

  const currentPurpose = purposes.find((p) => p.id === selectedPurposeId) ?? null;
  const [pendingAction, setPendingAction] = useState<'pause' | 'start' | null>(null);
  const [modePending, setModePending] = useState(false);

  const handlePause = async () => {
    if (!selectedPurposeId) return;
    setPendingAction('pause');
    const toastId = toast.loading('Zweck wird pausiert …');
    try {
      await pausePurpose(selectedPurposeId);
      toast.success('Zweck pausiert.', { id: toastId });
    } catch {
      toast.error('Pausieren fehlgeschlagen.', { id: toastId });
    } finally {
      setPendingAction(null);
    }
  };

  const handleStart = async () => {
    if (!selectedPurposeId) return;
    setPendingAction('start');
    const toastId = toast.loading('Zweck wird gestartet …');
    try {
      await startPurpose(selectedPurposeId);
      toast.success('Zweck gestartet.', { id: toastId });
    } catch {
      toast.error('Starten fehlgeschlagen.', { id: toastId });
    } finally {
      setPendingAction(null);
    }
  };

  const handleModeChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newMode = event.target.value as 'manual' | 'auto';
    if (!selectedPurposeId || currentPurpose?.mode === newMode) {
      return;
    }
    try {
      setModePending(true);
      await updatePurposeMode(selectedPurposeId, newMode);
      toast.success(
        `Modus auf "${newMode === 'auto' ? 'Automatisch' : 'Manuell'}" gesetzt.`,
      );
    } catch {
      toast.error('Modusänderung fehlgeschlagen.');
    } finally {
      setModePending(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <label
          className="text-sm font-semibold text-slate-700 dark:text-slate-200"
          htmlFor="pipeline-purpose-select"
        >
          Zweck
        </label>
        <select
          id="pipeline-purpose-select"
          className="min-w-[12rem] rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm transition focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
          value={selectedPurposeId || ''}
          onChange={(e) => setSelectedPurpose(e.target.value)}
        >
          <option value="" disabled>
            -- Zweck wählen --
          </option>
          {purposes.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      {!selectedPurposeId ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Wähle einen Purpose aus, um die Pipeline zu steuern.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handlePause}
              disabled={!!pendingAction}
              className="rounded-md bg-rose-500 px-3 py-1.5 font-medium text-white shadow-sm transition hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Pause Zweck
            </button>
            <button
              type="button"
              onClick={handleStart}
              disabled={!!pendingAction}
              className="rounded-md bg-emerald-500 px-3 py-1.5 font-medium text-white shadow-sm transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Start Zweck
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Modus
            </span>
            <select
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm shadow-sm focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              value={currentPurpose?.mode ?? 'manual'}
              onChange={handleModeChange}
              disabled={modePending}
            >
              <option value="manual">Manuell</option>
              <option value="auto">Automatisch</option>
            </select>
          </div>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {currentPurpose?.mode === 'auto'
              ? 'Automatische Ausführung aktiv'
              : 'Manuelle Steuerung aktiv'}
          </span>
        </div>
      )}
    </div>
  );
}
