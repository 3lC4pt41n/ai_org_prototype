import { FormEvent, useEffect, useMemo, useState } from 'react';
import type { PhaseViewContext, PipelineTemplateSummary } from '../types';

export function PurposePhaseContent({
  purposes,
  selectedPurpose,
  selectedPurposeId,
  onCreatePurpose,
  creatingPurpose,
  templates = [],
  defaultTemplateId,
}: PhaseViewContext) {
  const [newPurposeName, setNewPurposeName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');

  const templateOptions = useMemo(() => {
    const list = Array.isArray(templates) ? templates : [];
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }, [templates]);

  useEffect(() => {
    if (!templateOptions.length) {
      setSelectedTemplateId('');
      return;
    }
    const preferred =
      defaultTemplateId && templateOptions.some((tpl) => tpl.id === defaultTemplateId)
        ? defaultTemplateId
        : templateOptions[0].id;
    setSelectedTemplateId(preferred);
  }, [defaultTemplateId, templateOptions]);

  const selectedTemplate: PipelineTemplateSummary | undefined = useMemo(
    () => templateOptions.find((tpl) => tpl.id === selectedTemplateId),
    [selectedTemplateId, templateOptions],
  );

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = newPurposeName.trim();
    if (!value || !onCreatePurpose) {
      return;
    }
    setSubmitting(true);
    try {
      const ok = await onCreatePurpose(value, selectedTemplateId || undefined);
      if (ok) {
        setNewPurposeName('');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const isBusy = creatingPurpose || submitting;

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
        <form
          onSubmit={handleCreate}
          className="mt-4 flex flex-col gap-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-sm dark:border-slate-600 dark:bg-slate-900/40"
        >
          <label
            htmlFor="pipeline-new-purpose"
            className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
          >
            Neues Projektziel anlegen
          </label>
          <div className="flex flex-col gap-2">
            <label
              htmlFor="pipeline-template-select"
              className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500"
            >
              Pipeline-Vorlage
            </label>
            <select
              id="pipeline-template-select"
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm transition focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              value={selectedTemplateId}
              onChange={(event) => setSelectedTemplateId(event.target.value)}
              disabled={isBusy || templateOptions.length === 0}
            >
              {templateOptions.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.name}
                  {tpl.is_default ? ' • Standard' : ''}
                </option>
              ))}
            </select>
            {selectedTemplate?.description && (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {selectedTemplate.description}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              id="pipeline-new-purpose"
              type="text"
              value={newPurposeName}
              onChange={(e) => setNewPurposeName(e.target.value)}
              placeholder="Projektziel benennen"
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm transition focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              disabled={isBusy || !onCreatePurpose}
            />
            <button
              type="submit"
              className="inline-flex items-center justify-center rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isBusy || !onCreatePurpose || !newPurposeName.trim()}
            >
              Anlegen
            </button>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Das neue Projektziel startet automatisch mit der Vision-Phase der gewählten Vorlage.
          </p>
        </form>
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
