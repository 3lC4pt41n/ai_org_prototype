import { useEffect, useState, useRef, useMemo, type ChangeEvent } from 'react';
import { API_BASE } from '../lib/api';
import FileViewer from './FileViewer';
import usePipelineStore from '../store/pipelineStore';

interface Artifact {
  id: string;
  url?: string;
  released?: boolean;
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
}: Props) {
  const [content, setContent] = useState<string>('');
  const [contentType, setContentType] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

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
      // Build URL using API_BASE so it works both in dev (proxy) and production.
      // The backend returns url as "/api/artifact/{id}" – strip the /api prefix to avoid duplication.
      let url: string;
      if (artObj?.url) {
        const stripped = artObj.url.replace(/^\/api\//, '/');
        url = `${API_BASE}${stripped.startsWith('/') ? stripped : `/${stripped}`}`;
      } else {
        url = `${API_BASE}/artifact/${artifactId}`;
      }
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

      {/* Freigegeben-Status (nur Anzeige – Freigabe läuft über den Chat-Panel-Button) */}
      {showFeedback && isLatestVersion && currentArtifact.released && (
        <div className="p-3 border rounded bg-white flex items-center gap-2">
          <span className="text-green-600 text-sm font-medium">✓ Freigegeben</span>
        </div>
      )}
    </section>
  );
}
