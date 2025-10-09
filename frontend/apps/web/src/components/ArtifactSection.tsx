import { useEffect, useState, useRef, useMemo, type ChangeEvent } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api, postJson } from '../lib/api';
import { toast } from 'react-hot-toast';
import FileViewer from './FileViewer';
import usePipelineStore from '../store/pipelineStore';

interface Artifact {
  id: string;
  url?: string;
  released?: boolean;
}

interface FeedbackEntry {
  id?: string;
  content: string;
  created_at?: string;
  author?: string;
  role?: 'user' | 'assistant' | 'agent';
  intent?: 'feedback' | 'note' | 'question' | 'approval';
  metadata?: Record<string, unknown> | null;
}

interface Props {
  title: string;
  artifact: Artifact;
  statusIcon: React.ReactNode;
  /** zeige Eingabe nur, wenn pausiert */
  showFeedback?: boolean;
  onApproved?: (payload: { redirectArtifactId?: string; redirectArtifactUrl?: string }) => void;
}

export default function ArtifactSection({
  title,
  artifact,
  statusIcon,
  showFeedback = false,
  onApproved,
}: Props) {
  const [content, setContent] = useState<string>('');
  const [contentType, setContentType] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [history, setHistory] = useState<FeedbackEntry[]>([]);
  const [draft, setDraft] = useState<string>('');
  const [submitState, setSubmitState] = useState<'idle' | 'ok' | 'err'>('idle');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const historyEndRef = useRef<HTMLDivElement | null>(null);

  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchBacklog = usePipelineStore((s) => s.fetchBacklog);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);
  const selectedPurposeId = usePipelineStore((s) => s.selectedPurposeId);
  const allArtifacts = usePipelineStore((s) => s.artifacts);
  // Determine version history for this artifact (all artifacts of same task)
  interface ArtifactFull extends Artifact {
    task_id: string;
    repo_path: string;
    created_at?: string;
    media_type: string;
  }
  const artifactVersions: ArtifactFull[] = useMemo(() => {
    const list = (allArtifacts as ArtifactFull[]).filter(
      (a) => a.task_id === (artifact as any).task_id,
    );
    // defensiv kopieren vor Sort (keine Mutation von Store-Arrays)
    return [...list].sort(
      (a, b) =>
        new Date(a.created_at ?? 0).getTime() - new Date(b.created_at ?? 0).getTime(),
    );
  }, [allArtifacts, (artifact as any).task_id]);

  const [selectedArtifactId, setSelectedArtifactId] = useState<string>(artifact.id);
  const currentArtifact =
    artifactVersions.find((a) => a.id === selectedArtifactId) || (artifact as ArtifactFull);
  const filename = currentArtifact?.url ? currentArtifact.url.split('/').pop() || null : null;

  const fetchAbortRef = useRef<AbortController | null>(null);
  async function fetchVersionContent(artifactId: string) {
    fetchAbortRef.current?.abort();
    const controller = new AbortController();
    fetchAbortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const artObj = artifactVersions.find((a) => a.id === artifactId);
      const url = artObj?.url ? artObj.url : `/api/artifact/${artifactId}`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`artifact ${res.status}`);
      const ct = res.headers.get('content-type');
      setContentType(ct);
      if (
        ct?.startsWith('text/') ||
        ct?.includes('json') ||
        ct?.includes('xml') ||
        ct?.includes('yaml') ||
        ct?.includes('markdown') ||
        ct?.includes('javascript')
      ) {
        const text = await res.text();
        setContent(text);
        if (blobUrl) {
          URL.revokeObjectURL(blobUrl);
          setBlobUrl(null);
        }
      } else {
        const b = await res.blob();
        const urlObj = URL.createObjectURL(b);
        if (blobUrl) URL.revokeObjectURL(blobUrl);
        setBlobUrl(urlObj);
        setContent('');
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setContent('');
      setError('Artefakt konnte nicht geladen werden.');
    } finally {
      if (fetchAbortRef.current === controller) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    fetchVersionContent(selectedArtifactId);
    return () => {
      fetchAbortRef.current?.abort();
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedArtifactId]);

  // Update selected version if artifact prop changes (e.g., new version created)
  useEffect(() => {
    setSelectedArtifactId(artifact.id);
  }, [artifact.id]);

  function handleVersionChange(e: ChangeEvent<HTMLSelectElement>) {
    setSelectedArtifactId(e.target.value);
  }

  function handlePrevNext(dir: 'prev' | 'next') {
    const idx = artifactVersions.findIndex((a) => a.id === selectedArtifactId);
    const newIdx = dir === 'prev' ? idx - 1 : idx + 1;
    if (newIdx >= 0 && newIdx < artifactVersions.length) {
      setSelectedArtifactId(artifactVersions[newIdx].id);
    }
  }

  const isLatestVersion =
    artifactVersions.length > 0 &&
    selectedArtifactId === artifactVersions[artifactVersions.length - 1].id;
  const latestId =
    artifactVersions.length > 0 ? artifactVersions[artifactVersions.length - 1].id : null;

  // Feedback-Historie laden (neueste zuletzt)
  useEffect(() => {
    let alive = true;
    async function load() {
      if (!selectedPurposeId) {
        setHistory([]);
        return;
      }
      try {
        const params = new URLSearchParams({
          purpose_id: selectedPurposeId,
          artifact_id: artifact.id,
        });
        const r = await api.get(`/chat/messages?${params.toString()}`);
        const list: FeedbackEntry[] = Array.isArray(r.data) ? r.data : [];
        if (!alive) return;
        setHistory(list);
      } catch {
        if (!alive) return;
        setHistory([]);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [artifact.id, selectedPurposeId]);

  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history.length]);

  async function sendFeedback() {
    if (!draft.trim()) {
      toast.error('Bitte einen Korrekturvorschlag eingeben.');
      return;
    }
    if (!selectedPurposeId) {
      toast.error('Kein Projekt ausgewählt.');
      return;
    }
    setSubmitting(true);
    setSubmitState('idle');
    const tId = toast.loading('Korrektur wird gespeichert …');
    try {
      const message = draft.trim();
      const intent = /\?\s*$/.test(message) ? 'question' : 'feedback';
      await postJson(`/chat/messages`, {
        purpose_id: selectedPurposeId,
        artifact_ids: [artifact.id],
        message,
        intent,
      });
      setDraft('');
      setSubmitState('ok');
      toast.success('Korrekturvorschlag gespeichert – Product Owner aktualisiert das PRD.', { id: tId });
      // neu laden
      const params = new URLSearchParams({
        purpose_id: selectedPurposeId,
        artifact_id: artifact.id,
      });
      const r = await api.get(`/chat/messages?${params.toString()}`);
      const list: FeedbackEntry[] = Array.isArray(r.data) ? r.data : [];
      setHistory(list);
      await fetchVersionContent(selectedArtifactId);
    } catch {
      setSubmitState('err');
      toast.error('Speichern fehlgeschlagen.', { id: tId });
    } finally {
      setSubmitting(false);
    }
  }

  async function approve() {
    setSubmitState('idle');
    setSubmitting(true);
    const tId = toast.loading('Freigabe wird verarbeitet …');
    try {
      if (!selectedPurposeId) {
        throw new Error('purpose_missing');
      }
      const resp = await postJson<{
        status?: string;
        artifact_redirect_id?: string;
        artifact_redirect_url?: string;
      }>(`/chat/messages`, {
        purpose_id: selectedPurposeId,
        artifact_ids: [artifact.id],
        intent: 'approval',
        message: 'Approved',
      });
      setDraft('');
      setSubmitState('ok');
      toast.success('Freigegeben – Architektur wird erstellt & Plan erzeugt.', { id: tId });
      // Refresh lists
      await fetchArtifacts();
      await fetchBacklog();
      if (selectedPurposeId) {
        await fetchGraphAndStatus(selectedPurposeId);
      }
      const redirectArtifactId = resp?.artifact_redirect_id;
      const redirectArtifactUrl = resp?.artifact_redirect_url;
      onApproved?.({
        redirectArtifactId: redirectArtifactId ?? undefined,
        redirectArtifactUrl: redirectArtifactUrl ?? undefined,
      });
      if (redirectArtifactId) {
        toast.success('Architekturvorschlag erstellt – Architekturphase geöffnet.');
      }
      try {
        await fetchVersionContent(selectedArtifactId);
      } catch {
        /* ignore load error */
      }
    } catch {
      setSubmitState('err');
      toast.error('Freigabe fehlgeschlagen.', { id: tId });
    } finally {
      setSubmitting(false);
    }
  }

  function renderFeedback(fb: FeedbackEntry) {
    if (!fb.content) {
      return <p className="text-sm text-gray-500 italic">(kein Inhalt)</p>;
    }
    try {
      const parsed = JSON.parse(fb.content);
      if (Array.isArray(parsed)) {
        return (
          <ul className="list-disc ml-4 text-sm">
            {parsed.map((qa: any, i: number) => (
              <li key={i} className="mb-1">
                <p>
                  <b>Q:</b> {qa.question}
                </p>
                <p>
                  <b>A:</b> {qa.answer}
                </p>
              </li>
            ))}
          </ul>
        );
      }
    } catch {
      /* ignore – treat as markdown */
    }
    return (
      <ReactMarkdown className="prose prose-slate" remarkPlugins={[remarkGfm]}>
        {fb.content}
      </ReactMarkdown>
    );
  }

  return (
    <section className="mb-6 pb-6 border-b">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <span>{statusIcon}</span>
        {title}
      </h2>
      {/* Version selector */}
      {artifactVersions.length > 1 && (
        <div className="mb-2 flex items-center gap-2">
          <label className="text-sm font-medium">Version:</label>
          <button
            className="text-sm border border-gray-300 rounded px-2 py-1 disabled:opacity-50"
            onClick={() => handlePrevNext('prev')}
            disabled={artifactVersions[0].id === selectedArtifactId}
            aria-label="Vorherige Version"
          >
            Vorherige
          </button>
          <select
            className="text-sm border border-gray-300 rounded px-2 py-1"
            value={selectedArtifactId}
            onChange={handleVersionChange}
            aria-label="Version auswählen"
          >
            {artifactVersions.map((art, idx) => {
              const versionNum = idx + 1;
              const dateStr = art.created_at
                ? new Date(art.created_at).toLocaleString('de-DE', {
                    dateStyle: 'short',
                    timeStyle: 'short',
                  })
                : null;
              let label = `Version ${versionNum}`;
              if (idx === 0) label += ' (älteste)';
              if (idx === artifactVersions.length - 1) label += ' (aktuell)';
              if (dateStr) label += ` – erstellt am ${dateStr}`;
              return (
                <option value={art.id} key={art.id}>
                  {label}
                </option>
              );
            })}
          </select>
          <button
            className="text-sm border border-gray-300 rounded px-2 py-1 disabled:opacity-50"
            onClick={() => handlePrevNext('next')}
            disabled={artifactVersions[artifactVersions.length - 1].id === selectedArtifactId}
            aria-label="Nächste Version"
          >
            Nächste
          </button>
        </div>
      )}
      {/* Hinweis bei älteren Versionen */}
      {!isLatestVersion && (
        <div className="mb-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Sie betrachten eine <b>ältere Version</b> (Nur-Leseansicht).{' '}
          {latestId && (
            <button
              className="underline hover:no-underline"
              onClick={() => setSelectedArtifactId(latestId)}
              aria-label="Zur neuesten Version springen"
              title="Zur neuesten Version springen"
            >
              Zur neuesten Version wechseln
            </button>
          )}
        </div>
      )}

      <div className="mb-3 p-3 border rounded bg-white">
        {loading ? (
          <p className="text-sm text-gray-500">Lade…</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : (
          <FileViewer
            text={content}
            blobUrl={blobUrl}
            contentType={contentType}
            filename={filename}
            height={520}
          />
        )}
      </div>

      {/* Feedback-Historie */}
      {history.length > 0 && isLatestVersion && (
        <div className="mb-3 p-3 border rounded bg-white space-y-3 max-h-60 overflow-y-auto">
          {history.map((fb, idx) => {
            const key = fb.id ?? `${idx}`;
            const intentLabel =
              fb.intent === 'feedback'
                ? 'Feedback'
                : fb.intent === 'question'
                ? 'Frage'
                : fb.intent === 'approval'
                ? 'Freigabe'
                : fb.intent === 'note'
                ? 'Notiz'
                : null;
            const authorLabel =
              fb.author ||
              (fb.role === 'assistant'
                ? 'Product Owner (AI)'
                : fb.role === 'agent'
                ? 'Agent'
                : 'Du');
            const createdLabel = fb.created_at
              ? new Date(fb.created_at).toLocaleString('de-DE', {
                  dateStyle: 'short',
                  timeStyle: 'short',
                })
              : null;
            const bubbleClass =
              fb.role === 'user'
                ? 'border-blue-200 bg-blue-50'
                : fb.role === 'assistant'
                ? 'border-green-200 bg-green-50'
                : 'border-slate-200 bg-slate-50';
            return (
              <div key={key} className={`rounded border ${bubbleClass} p-2`}>
                <div className="text-xs text-gray-600 mb-1 flex flex-wrap items-center gap-1">
                  <span className="font-medium">{authorLabel}</span>
                  {intentLabel && (
                    <span className="text-[10px] uppercase tracking-wide text-gray-500">{intentLabel}</span>
                  )}
                  {createdLabel && <span className="text-[11px] text-gray-500">{createdLabel}</span>}
                </div>
                {renderFeedback(fb)}
              </div>
            );
          })}
          <div ref={historyEndRef} />
        </div>
      )}

      {/* Eingabe (nur bei Pause) */}
      {showFeedback && isLatestVersion && (
        <div className="p-3 border rounded bg-white">
          <label className="block text-sm font-medium mb-1">Dein Korrekturvorschlag</label>
          <textarea
            rows={4}
            className="w-full p-2 border rounded text-sm"
            placeholder="Schreibe einen Korrekturvorschlag oder eine Rückfrage…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
              onClick={sendFeedback}
              disabled={!draft.trim() || submitting}
            >
              Korrektur anfordern
            </button>
            {!currentArtifact.released ? (
              <button
                className="px-3 py-1 bg-green-600 text-white rounded text-sm"
                onClick={approve}
                disabled={submitting}
              >
                Freigeben
              </button>
            ) : (
              <span className="text-green-600 text-sm">Freigegeben</span>
            )}
            {submitState === 'ok' && <span className="text-green-600 text-xs">Gespeichert.</span>}
            {submitState === 'err' && (
              <span className="text-red-600 text-xs">Speichern fehlgeschlagen.</span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
