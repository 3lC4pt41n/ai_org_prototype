import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'react-hot-toast';
import { PlayCircle, PauseCircle, Trash2, ChevronRight } from 'lucide-react';
import usePipelineStore from '../../../store/pipelineStore';
import { API_BASE, getJson, postJson } from '../../../lib/api';
import type {
  PhaseViewContext,
  PipelineTemplateSummary,
  ArtifactItem,
} from '../types';

type TopTab = 'new' | 'list' | 'details';

async function delJson(path: string) {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) throw new Error(`DELETE ${path} failed`);
  try {
    return await res.json();
  } catch {
    return {};
  }
}

export function PurposePhaseContent(ctx: PhaseViewContext) {
  const purposes = ctx.purposes ?? [];
  const artifacts = (ctx.artifacts ?? []) as ArtifactItem[];
  const fetchPurposes = usePipelineStore((s) => s.fetchPurposes);
  const setSelectedPurpose = usePipelineStore((s) => s.setSelectedPurpose);
  const selectedPurposeId = ctx.selectedPurposeId ?? null;
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchBacklog = usePipelineStore((s) => s.fetchBacklog);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);

  const [tab, setTab] = useState<TopTab>('new');

  const [purposeName, setPurposeName] = useState('');
  const [mode, setMode] = useState<'manual' | 'auto'>('manual');
  const [templates, setTemplates] = useState<PipelineTemplateSummary[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateId, setTemplateId] = useState<string>('');

  const [history, setHistory] = useState<any[]>([]);

  const selectedPurpose =
    purposes.find((p: any) => p.id === selectedPurposeId) ?? null;

  const released = artifacts.filter((a) => a.released);
  const drafts = artifacts.filter((a) => !a.released);

  useEffect(() => {
    let active = true;
    setTemplatesLoading(true);
    getJson<PipelineTemplateSummary[]>('/pipeline/templates')
      .then((data) => active && setTemplates(Array.isArray(data) ? data : []))
      .catch(() => active && setTemplates([]))
      .finally(() => active && setTemplatesLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const defaultTemplateId = useMemo(() => {
    if (!templates.length) return '';
    const tTenant = templates.find((t) => t.is_default && t.tenant_id);
    if (tTenant) return tTenant.id;
    const tGlobal = templates.find((t) => t.is_default);
    return (tGlobal ?? templates[0]).id;
  }, [templates]);

  useEffect(() => {
    if (!templateId && defaultTemplateId) {
      setTemplateId(defaultTemplateId);
    }
  }, [templateId, defaultTemplateId]);

  useEffect(() => {
    if (!selectedPurposeId) return;
    fetchArtifacts();
    fetchBacklog();
    fetchGraphAndStatus(selectedPurposeId);
    const controller = new AbortController();
    const signal = controller.signal;
    getJson<any>(`/purposes/${selectedPurposeId}/status`, { signal })
      .then((rows) => setHistory(Array.isArray(rows) ? rows : []))
      .catch(() => setHistory([]));
    const iv = setInterval(() => {
      fetchArtifacts();
      fetchGraphAndStatus(selectedPurposeId);
    }, 6000);
    return () => {
      controller.abort();
      clearInterval(iv);
    };
  }, [selectedPurposeId, fetchArtifacts, fetchBacklog, fetchGraphAndStatus]);

  const handleCreate = useCallback(async () => {
    const name = purposeName.trim();
    if (!name) {
      toast.error('Bitte gib ein Projektziel ein.');
      return;
    }
    const ok = await ctx.onCreatePurpose?.(name, templateId || undefined);
    if (ok) {
      try {
        const token = localStorage.getItem('token');
        const id = usePipelineStore.getState().selectedPurposeId;
        if (mode !== 'manual' && id) {
          await fetch(`${API_BASE}/purposes/${id}`, {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ mode }),
          });
        }
      } catch {
        /* ignore */
      }
      setPurposeName('');
      setMode('manual');
      setTemplateId(defaultTemplateId || '');
      setTab('details');
      fetchPurposes();
    }
  }, [purposeName, mode, templateId, ctx.onCreatePurpose, fetchPurposes, defaultTemplateId]);

  const handleStart = useCallback(
    async (id: string) => {
      try {
        await postJson(`/purposes/${id}/start`, {});
        toast.success('Gestartet.');
        if (id === selectedPurposeId) {
          await fetchGraphAndStatus(id);
        }
      } catch {
        toast.error('Start fehlgeschlagen.');
      }
    },
    [selectedPurposeId, fetchGraphAndStatus],
  );

  const handlePause = useCallback(
    async (id: string) => {
      try {
        await postJson(`/purposes/${id}/pause`, {});
        toast.success('Pausiert.');
        if (id === selectedPurposeId) {
          await fetchGraphAndStatus(id);
        }
      } catch {
        toast.error('Pause fehlgeschlagen.');
      }
    },
    [selectedPurposeId, fetchGraphAndStatus],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      if (!confirm('Dieses Projektziel endgültig löschen?')) return;
      try {
        await delJson(`/purposes/${id}`);
        toast.success('Gelöscht.');
        if (id === selectedPurposeId) {
          usePipelineStore.setState({
            selectedPurposeId: null,
            selectedArtifactId: null,
            artifactContent: '',
            feedbacks: [],
          });
          setTab('list');
        }
        await fetchPurposes();
      } catch {
        toast.error('Löschen fehlgeschlagen.');
      }
    },
    [selectedPurposeId, fetchPurposes],
  );

  const downloadArtifactFile = (artifactId: string, filename: string) => {
    const token = localStorage.getItem('token');
    fetch(`${API_BASE}/artifact/${artifactId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error('Download fehlgeschlagen');
        return res.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(() => toast.error('Download fehlgeschlagen'));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {(['new', 'list', 'details'] as TopTab[]).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              tab === key
                ? 'bg-amber-500 text-white'
                : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'
            }`}
          >
            {key === 'new' && 'Neu'}
            {key === 'list' && 'Liste'}
            {key === 'details' && 'Details'}
          </button>
        ))}
      </div>

      {tab === 'new' && (
        <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Projektziel / Zweck
              </label>
              <input
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                placeholder="Beschreibe kurz dein Ziel …"
                value={purposeName}
                onChange={(e) => setPurposeName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Modus
              </label>
              <select
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                value={mode}
                onChange={(e) => setMode(e.target.value as 'manual' | 'auto')}
              >
                <option value="manual">Manuell</option>
                <option value="auto">Automatisch</option>
              </select>
            </div>
            <div className="md:col-span-3">
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Pipeline‑Vorlage
              </label>
              <select
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                disabled={templatesLoading}
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
              >
                {(templates ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} {t.is_default ? '• Standard' : ''}
                  </option>
                ))}
                {!templates.length && <option value="">Keine Vorlagen verfügbar</option>}
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
            >
              Anlegen
            </button>
          </div>
        </section>
      )}

      {tab === 'list' && (
        <section className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Projektziel</th>
                <th className="px-3 py-2 text-left font-semibold">Modus</th>
                <th className="px-3 py-2 text-left font-semibold">Erstellt</th>
                <th className="px-3 py-2 text-left font-semibold">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {(purposes as any[]).map((p) => (
                <tr key={p.id} className="text-slate-700 dark:text-slate-200">
                  <td className="px-3 py-2">{p.purpose ?? p.name ?? '—'}</td>
                  <td className="px-3 py-2 uppercase">{(p.mode ?? 'manual').toString()}</td>
                  <td className="px-3 py-2">
                    {p.created_at ? new Date(p.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        className="inline-flex items-center gap-1 rounded bg-amber-500 px-2 py-1 text-xs font-semibold text-white hover:bg-amber-600"
                        onClick={() => {
                          setSelectedPurpose(p.id);
                          setTab('details');
                        }}
                        title="Öffnen"
                      >
                        <ChevronRight className="h-3 w-3" /> Öffnen
                      </button>
                      <button
                        className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
                        onClick={() => handleStart(p.id)}
                        title="Start"
                      >
                        <PlayCircle className="h-3 w-3" /> Start
                      </button>
                      <button
                        className="inline-flex items-center gap-1 rounded bg-slate-600 px-2 py-1 text-xs font-semibold text-white hover:bg-slate-700"
                        onClick={() => handlePause(p.id)}
                        title="Pause"
                      >
                        <PauseCircle className="h-3 w-3" /> Pause
                      </button>
                      <button
                        className="inline-flex items-center gap-1 rounded bg-rose-600 px-2 py-1 text-xs font-semibold text-white hover:bg-rose-700"
                        onClick={() => handleDelete(p.id)}
                        title="Löschen"
                      >
                        <Trash2 className="h-3 w-3" /> Löschen
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {(!purposes || (purposes as any[]).length === 0) && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-500">
                    Noch keine Projektziele vorhanden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}

      {tab === 'details' && (
        <section className="space-y-6">
          {!selectedPurpose ? (
            <p className="text-sm text-slate-500">Bitte in der Liste ein Projektziel auswählen.</p>
          ) : (
            <>
              <div className="flex flex-col justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900 md:flex-row md:items-center">
                <div>
                  <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                    {selectedPurpose.purpose ?? selectedPurpose.name ?? 'Projektziel'}
                  </h2>
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    Modus: <b>{selectedPurpose.mode ?? 'manual'}</b>{' '}
                    {selectedPurpose.created_at && (
                      <>· {new Date(selectedPurpose.created_at).toLocaleString()}</>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="inline-flex items-center gap-1 rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                    onClick={() => handleStart(selectedPurpose.id)}
                  >
                    <PlayCircle className="h-3 w-3" /> Starten
                  </button>
                  <button
                    className="inline-flex items-center gap-1 rounded bg-slate-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
                    onClick={() => handlePause(selectedPurpose.id)}
                  >
                    <PauseCircle className="h-3 w-3" /> Pausieren
                  </button>
                  <button
                    className="inline-flex items-center gap-1 rounded bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
                    onClick={() => handleDelete(selectedPurpose.id)}
                  >
                    <Trash2 className="h-3 w-3" /> Löschen
                  </button>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                  <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                    Aktuelle Artefakte (released)
                  </h3>
                  <ul className="space-y-2 text-sm">
                    {released.map((a) => (
                      <li
                        key={a.id}
                        className="flex items-center justify-between rounded border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                      >
                        <span className="truncate text-emerald-600">
                          {a.repo_path?.replace(/^[^/]+\//, '')}
                        </span>
                        <button
                          className="text-xs font-semibold text-amber-600 hover:underline"
                          onClick={() =>
                            downloadArtifactFile(
                              a.id,
                              a.repo_path?.split('/').pop() || a.id,
                            )
                          }
                        >
                          Download
                        </button>
                      </li>
                    ))}
                    {released.length === 0 && (
                      <li className="text-slate-500">Keine freigegebenen Artefakte.</li>
                    )}
                  </ul>
                </section>
                <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                  <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                    Entwürfe (draft)
                  </h3>
                  <ul className="space-y-2 text-sm">
                    {drafts.map((a) => (
                      <li
                        key={a.id}
                        className="flex items-center justify-between rounded border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                      >
                        <span className="truncate text-slate-700 dark:text-slate-200">
                          {a.repo_path?.replace(/^[^/]+\//, '')}
                        </span>
                        <span className="text-xs text-slate-500">draft</span>
                      </li>
                    ))}
                    {drafts.length === 0 && (
                      <li className="text-slate-500">Keine Entwürfe vorhanden.</li>
                    )}
                  </ul>
                </section>
              </div>

              <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                  Verlauf
                </h3>
                <ul className="space-y-1 text-sm">
                  {(history ?? []).map((row: any, idx: number) => (
                    <li key={idx} className="text-slate-600 dark:text-slate-300">
                      <span className="mr-2 inline-block rounded bg-slate-200 px-2 py-0.5 text-xs dark:bg-slate-700">
                        {row.status ?? row.state ?? 'status'}
                      </span>
                      {row.message ?? row.detail ?? ''}
                      {row.timestamp && (
                        <span className="ml-2 text-xs text-slate-400">
                          {new Date(row.timestamp).toLocaleString()}
                        </span>
                      )}
                    </li>
                  ))}
                  {(!history || history.length === 0) && (
                    <li className="text-slate-500">Noch kein Verlauf vorhanden.</li>
                  )}
                </ul>
              </section>
            </>
          )}
        </section>
      )}
    </div>
  );
}

export function PurposePhaseSidebar() {
  return (
    <aside className="text-sm text-slate-600 dark:text-slate-300">
      <p className="mb-1 font-medium">Projektziel</p>
      <p>Lege ein Ziel an (Neu), verwalte Ziele (Liste) oder öffne Details.</p>
    </aside>
  );
}
