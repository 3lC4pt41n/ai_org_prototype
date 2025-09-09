import { useEffect } from 'react';
import { History, Package } from 'lucide-react';
import { toast } from 'react-hot-toast';
import usePipelineStore from '../store/pipelineStore';
import PurposeSelector from '../components/PurposeSelector';
import ArtifactSection from '../components/ArtifactSection';
import GraphSection from '../components/GraphSection';
import { API_BASE } from '../lib/api';
import AImarChatPanel from '../components/AImarChatPanel';

interface ArtifactItem {
  id: string;
  repo_path?: string;
  url?: string;
  created_at?: string;
  media_type?: string;
  released?: boolean;
}

export default function PipelineView() {
  const artifacts = usePipelineStore((s) => s.artifacts) as ArtifactItem[];
  const backlog = usePipelineStore((s) => s.backlog);
  const purposes = usePipelineStore((s) => (s as any).purposes ?? []);
  const graphNodes = usePipelineStore((s) => s.graphNodes);
  const graphEdges = usePipelineStore((s) => s.graphEdges);
  const paused = usePipelineStore((s) => s.paused);
  const isLoading = usePipelineStore((s) => s.isLoading);
  const error = usePipelineStore((s) => s.error);
  const selectedPurposeId = usePipelineStore((s) => s.selectedPurposeId);
  const fetchPurposes = usePipelineStore((s) => s.fetchPurposes);
  const setSelectedPurpose = usePipelineStore((s) => s.setSelectedPurpose);
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchBacklog = usePipelineStore((s) => s.fetchBacklog);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);

  useEffect(() => {
    fetchPurposes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchPurposes]);

  useEffect(() => {
    if (!selectedPurposeId && purposes.length > 0) {
      setSelectedPurpose(purposes[0].id);
    }
  }, [purposes, selectedPurposeId, setSelectedPurpose]);

  useEffect(() => {
    if (!selectedPurposeId) return;
    const controller = new AbortController();
    const signal = controller.signal;
    fetchArtifacts(signal);
    fetchBacklog(signal);
    fetchGraphAndStatus(selectedPurposeId, signal);
    return () => controller.abort();
  }, [selectedPurposeId, fetchArtifacts, fetchBacklog, fetchGraphAndStatus]);

  const prdArtifact = artifacts.find((a) =>
    a.repo_path?.toLowerCase().includes('product_requirements'),
  );
  const archArtifact = artifacts.find((a) =>
    a.repo_path?.toLowerCase().includes('architecture_blueprint'),
  );

  const prdPending = paused && !archArtifact; // bleibt für Status-Icon Logik bestehen
  const archPending = paused && !!archArtifact;
  const prdStatusIcon = prdPending ? '🕓' : '✅';
  const archStatusIcon = archArtifact ? (archPending ? '🕓' : '✅') : '✅';
  const graphStatusIcon = paused ? '🕓' : '✅';

  const statusInfo: Record<string, { label: string; color: string }> = {
    todo: { label: 'Todo', color: 'bg-yellow-500 text-black' },
    doing: { label: 'In Progress', color: 'bg-blue-500 text-white' },
    done: { label: 'Done', color: 'bg-green-600 text-white' },
    failed: { label: 'Failed', color: 'bg-red-600 text-white' },
    blocked: { label: 'Blocked', color: 'bg-gray-500 text-white' },
    skipped: { label: 'Skipped', color: 'bg-gray-500 text-white' },
    budget_exceeded: {
      label: 'Blocked (Budget)',
      color: 'bg-gray-500 text-white',
    },
  };

  function downloadArtifactFile(artifactId: string, filename: string) {
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
  }

  return (
    <div className="flex flex-col h-screen">
      <div className="p-4 bg-gray-100 flex justify-between items-center gap-2">
        <PurposeSelector />
        {/* Pause/Resume handled in AdminDashboard; hier nur Anzeige */}
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 border-b">
          {typeof error === 'string'
            ? error
            : error instanceof Error
              ? error.message
              : String(error)}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <div className="main-panel flex-1 overflow-y-auto p-4">
          {isLoading && <p className="text-gray-500">Lade...</p>}
          {/* Show feedback UI for PRD only if paused and waiting on PRD (no architecture yet) */}
          {prdArtifact && (
            <ArtifactSection
              title="Product Requirements Document"
              artifact={prdArtifact}
              statusIcon={prdStatusIcon}
              showFeedback={prdPending}
            />
          )}
          {archArtifact && (
            <ArtifactSection
              title="Architektur"
              artifact={archArtifact}
              statusIcon={archStatusIcon}
              showFeedback={archPending}
            />
          )}
          <GraphSection statusIcon={graphStatusIcon} nodes={graphNodes} edges={graphEdges} />
          {selectedPurposeId && (
            <AImarChatPanel purposeId={selectedPurposeId} paused={paused} />
          )}
        </div>

        <aside className="w-80 border-l bg-gray-50 p-4 overflow-y-auto">
          <h2 className="flex items-center gap-2 text-lg mb-2">
            <History className="w-4 h-4" /> Backlog
          </h2>
          <ul className="space-y-1 text-sm">
            {backlog.map((t: any) => (
              <li
                key={t.id}
                className="border-b border-slate-200 py-1 flex items-center justify-between"
              >
                <div>
                  <span className="text-amber-400 font-mono mr-2">{t.id}</span>
                  {t.description}
                </div>
                <span
                  className={`ml-2 px-2 py-0.5 rounded ${
                    statusInfo[t.status]?.color
                  } text-xs font-semibold`}
                >
                  {statusInfo[t.status]?.label ?? t.status}
                </span>
              </li>
            ))}
            {backlog.length === 0 && <li className="italic">Queue is empty 🎉</li>}
          </ul>

          <h2 className="flex items-center gap-2 text-lg mt-4 mb-2">
            <Package className="w-4 h-4" /> Artifacts
          </h2>
          <ul className="space-y-1 text-sm">
            {artifacts.map((a) => (
              <li key={a.id} className="border-b border-slate-200 py-1">
                <span className="text-amber-400 font-mono mr-2">{a.task_id}</span>
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    downloadArtifactFile(a.id, a.repo_path?.split('/').pop() || a.id);
                  }}
                  className="text-amber-400 hover:underline"
                >
                  {a.repo_path?.replace(/^[^/]+\//, '')}
                </a>{' '}
                <span className="text-slate-600 text-xs">
                  ({a.media_type}, {new Date(a.created_at!).toLocaleString()})
                </span>
                {a.released && <span className="ml-1 text-green-600 text-xs">released</span>}
              </li>
            ))}
            {artifacts.length === 0 && <li className="italic">No artifacts yet</li>}
          </ul>
        </aside>
      </div>
    </div>
  );
}
