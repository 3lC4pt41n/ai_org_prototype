import React, { useCallback, useEffect, useState } from 'react';
import ReactFlow, { Background, Controls, Edge, Node, useEdgesState, useNodesState } from 'reactflow';
import 'reactflow/dist/style.css';
import { Toaster, toast } from 'react-hot-toast';
import { ChevronRight, Pause, Play, RefreshCw, UploadCloud } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

// -- Leichte UI-Bausteine (keine externe Abhängigkeit) -----------------------
const HStack: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ children, className = '', ...rest }) => (
  <div className={`flex items-center gap-2 ${className}`} {...rest}>{children}</div>
);
const VStack: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ children, className = '', ...rest }) => (
  <div className={`flex flex-col gap-3 ${className}`} {...rest}>{children}</div>
);
const Card: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ children, className = '', ...rest }) => (
  <div className={`rounded-md border border-slate-200 bg-white p-3 shadow-sm ${className}`} {...rest}>{children}</div>
);
const Button: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ children, className = '', ...rest }) => (
  <button className={`inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 active:translate-y-[0.5px] ${className}`} {...rest}>
    {children}
  </button>
);
const Input: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = ({ className = '', ...rest }) => (
  <input className={`w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-slate-200 ${className}`} {...rest} />
);
const TextArea: React.FC<React.TextareaHTMLAttributes<HTMLTextAreaElement>> = ({ className = '', ...rest }) => (
  <textarea className={`w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-slate-200 ${className}`} {...rest} />
);

// -- API helpers ---------------------------------------------------------------
async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: 'include' });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}
async function postJson<T>(url: string, body?: any, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
    ...(opts ?? {}),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}${text ? ` – ${text}` : ''}`);
  }
  return (await res.json().catch(() => ({}))) as T;
}
function downloadUrl(url: string) {
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noreferrer';
  a.click();
}

// -- Types ---------------------------------------------------------------------
type Purpose = { id: string; name: string; is_active?: boolean };
type Artifact = {
  id: string;
  task_id?: string;
  repo_path: string;
  media_type?: string;
  size?: number;
  sha256?: string;
  created_at?: string;
};
type Task = { id: string; description: string; status: 'todo' | 'doing' | 'done'; owner?: string };

// -- Helpers -------------------------------------------------------------------
const byName = (a: Purpose, b: Purpose) => a.name.localeCompare(b.name);
const nameFromRepoPath = (p: string) => (p.split(/[\\/]/).slice(-1)[0] || p);

// -- View ----------------------------------------------------------------------
export default function PipelineView() {
  const [search, setSearch] = useSearchParams();
  const [purposes, setPurposes] = useState<Purpose[]>([]);
  const [purposeId, setPurposeId] = useState<string | null>(null);
  const [purposeLoading, setPurposeLoading] = useState(false);

  // status + graph
  const [status, setStatus] = useState<any>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node[]>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge[]>([]);

  // backlog + artifacts
  const [backlog, setBacklog] = useState<Task[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [artifactText, setArtifactText] = useState<string>('');
  const [feedback, setFeedback] = useState<string>('');

  // new purpose
  const [newPurpose, setNewPurpose] = useState('');

  // Purposes laden & vorselektieren
  useEffect(() => {
    (async () => {
      try {
        const ps = await getJson<Purpose[]>('/api/purpose');
        ps.sort(byName);
        setPurposes(ps);
        const fromUrl = search.get('purpose');
        const fromStorage = localStorage.getItem('purposeId');
        const initial = fromUrl || fromStorage || (ps[0] ? ps[0].id : null);
        if (initial) {
          setPurposeId(initial);
          if (!fromUrl) setSearch({ purpose: initial }, { replace: true });
        }
      } catch (e) {
        console.error('purpose list failed', e);
        toast.error('Konnte Zwecke nicht laden.');
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Daten je Purpose laden
  useEffect(() => {
    if (!purposeId) return;
    localStorage.setItem('purposeId', purposeId);
    setPurposeLoading(true);
    const load = async () => {
      try {
        const [st, art] = await Promise.all([
          getJson<any>(`/api/purpose/${purposeId}/status`).catch(() => getJson<any>('/api/pause')),
          getJson<Artifact[]>(`/api/artifacts?purpose_id=${purposeId}`),
        ]);
        setStatus(st);
        setArtifacts(art);
        let graph: any | null = null;
        try { graph = await getJson<any>(`/api/purpose/${purposeId}/graph`); }
        catch { try { graph = await getJson<any>('/api/graph'); } catch { graph = null; } }
        if (graph && graph.nodes && graph.edges) {
          const n = (graph.nodes as any[]).map((n, i) => ({
            id: String(n.id ?? i),
            data: { label: n.label ?? n.description ?? n.name ?? `Task ${i + 1}` },
            position: { x: n.x ?? i * 120, y: n.y ?? (i % 5) * 90 },
          })) as Node[];
          const e = (graph.edges as any[]).map((e, i) => ({
            id: String(e.id ?? i),
            source: String(e.source),
            target: String(e.target),
            label: e.label ?? e.kind ?? '',
            animated: e.animated ?? false,
          })) as Edge[];
          setNodes(n); setEdges(e);
        } else { setNodes([]); setEdges([]); }
        try { setBacklog(await getJson<Task[]>(`/api/backlog?purpose_id=${purposeId}`)); }
        catch { setBacklog([]); }
      } catch (err) {
        console.error(err);
        toast.error('Konnte Pipeline-Daten nicht laden.');
      } finally { setPurposeLoading(false); }
    };
    load();
  }, [purposeId]);

  // Aktionen
  const pauseAll = useCallback(async () => { await postJson('/api/pause'); toast.success('Pipeline pausiert'); }, []);
  const resumeAll = useCallback(async () => { await postJson('/api/resume'); toast.success('Pipeline gestartet'); }, []);
  const pausePurpose = useCallback(async () => {
    if (!purposeId) return;
    try { await postJson(`/api/purpose/${purposeId}/pause`); }
    catch { await postJson(`/api/purposes/pause/${purposeId}`).catch(() => {}); }
    toast.success('Zweck pausiert');
  }, [purposeId]);
  const resumePurpose = useCallback(async () => {
    if (!purposeId) return;
    try { await postJson(`/api/purpose/${purposeId}/resume`); }
    catch { await postJson(`/api/purposes/start/${purposeId}`).catch(() => {}); }
    toast.success('Zweck gestartet');
  }, [purposeId]);
  const createPurpose = useCallback(async () => {
    if (!newPurpose.trim()) return;
    try {
      const res = await postJson<Purpose>('/api/purpose', { name: newPurpose.trim() });
      setNewPurpose(''); toast.success('Zweck angelegt');
      const ps = await getJson<Purpose[]>('/api/purpose'); ps.sort(byName); setPurposes(ps);
      setPurposeId(res.id); setSearch({ purpose: res.id }, { replace: true });
    } catch (e) { console.error(e); toast.error('Anlage fehlgeschlagen'); }
  }, [newPurpose, setSearch]);
  const openArtifact = useCallback(async (a: Artifact) => {
    setSelectedArtifact(a); setArtifactText(''); setFeedback('');
    try {
      const url = `/api/artifact/${a.id}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(String(res.status));
      const mt = (a.media_type || res.headers.get('Content-Type') || '').toLowerCase();
      if (mt.includes('text') || mt.includes('markdown') || mt.includes('json')) {
        setArtifactText(await res.text());
      } else { downloadUrl(url); }
    } catch (e) { console.warn('artifact fetch failed – fallback new tab', e); downloadUrl(`/api/artifact/${a.id}`); }
  }, []);
  const sendFeedback = useCallback(async () => {
    if (!selectedArtifact || !feedback.trim()) return;
    try {
      await postJson(`/api/feedback/${selectedArtifact.id}`, { feedback: feedback.trim() })
        .catch(async () => {
          if (!purposeId) throw new Error('no purpose');
          await postJson(`/api/purpose/${purposeId}/feedback`, { artifact_id: selectedArtifact.id, feedback: feedback.trim() });
        });
      toast.success('Feedback gesendet'); setFeedback('');
    } catch (e) { console.error(e); toast.error('Feedback fehlgeschlagen'); }
  }, [selectedArtifact, feedback, purposeId]);

  // Graph-Fallback aus Backlog
  useEffect(() => {
    if (nodes.length || !backlog.length) return;
    const bn: Node[] = backlog.map((t, i) => ({
      id: t.id,
      data: { label: `${t.description}` },
      position: { x: 80 + (i % 6) * 180, y: 80 + Math.floor(i / 6) * 120 },
      style: { borderColor: t.status === 'done' ? '#16a34a' : t.status === 'doing' ? '#f59e0b' : '#cbd5e1' },
    }));
    setNodes(bn); setEdges([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backlog]);

  // Render
  return (
    <div className="mx-auto max-w-[1400px] p-4">
      <Toaster position="top-right" />
      <VStack className="gap-4">
        {/* Toolbar */}
        <Card>
          <HStack className="justify-between">
            <HStack className="flex-1">
              <label className="text-sm text-slate-600">Zweck auswählen:</label>
              <select
                className="min-w-[280px] rounded-md border border-slate-300 px-2 py-1 text-sm"
                value={purposeId ?? ''}
                onChange={(e) => {
                  const id = e.target.value || null;
                  setPurposeId(id);
                  if (id) setSearch({ purpose: id }, { replace: true });
                }}
              >
                <option value="">– Zweck wählen –</option>
                {purposes.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
              </select>
              <Button onClick={pauseAll}><Pause className="h-4 w-4" /> Pause alle</Button>
              <Button onClick={resumeAll}><Play className="h-4 w-4" /> Start alle</Button>
              {purposeId && (
                <>
                  <Button onClick={pausePurpose}><Pause className="h-4 w-4" /> Pause Zweck</Button>
                  <Button onClick={resumePurpose}><Play className="h-4 w-4" /> Start Zweck</Button>
                </>
              )}
            </HStack>
            <HStack className="w-[420px] justify-end">
              <Input placeholder="Neues Projektziel…" value={newPurpose} onChange={(e) => setNewPurpose(e.target.value)} />
              <Button onClick={createPurpose}><ChevronRight className="h-4 w-4" /> Anlegen</Button>
            </HStack>
          </HStack>
        </Card>

        {/* Body */}
        <div className="grid grid-cols-12 gap-4">
          <Card className="col-span-8 h-[560px] overflow-hidden">
            <HStack className="justify-between pb-2">
              <div className="font-medium">Graph</div>
              <Button onClick={() => purposeId && setPurposeId(purposeId)}><RefreshCw className="h-4 w-4" /> Refresh</Button>
            </HStack>
            <div className="h-[500px] w-full rounded-md border">
              <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} fitView>
                <Background />
                <Controls />
              </ReactFlow>
            </div>
          </Card>
          <div className="col-span-4 flex flex-col gap-4">
            <Card className="max-h-[260px] overflow-auto">
              <div className="mb-2 font-medium">Backlog</div>
              {backlog.length === 0 ? (
                <div className="text-sm text-slate-500">{purposeLoading ? 'Lade…' : 'Kein Backlog.'}</div>
              ) : (
                <ul className="space-y-1">
                  {backlog.map((t) => (
                    <li key={t.id} className="flex items-center justify-between text-sm">
                      <span title={t.description} className="truncate">{t.description}</span>
                      <span className={`ml-2 rounded px-1.5 py-0.5 text-xs ${t.status === 'done' ? 'bg-green-100 text-green-700' : t.status === 'doing' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-700'}`}>
                        {t.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card className="max-h-[300px] overflow-auto">
              <div className="mb-2 font-medium">Artefakte</div>
              {artifacts.length === 0 ? (
                <div className="text-sm text-slate-500">{purposeLoading ? 'Lade…' : 'Keine Artefakte verfügbar.'}</div>
              ) : (
                <ul className="space-y-1">
                  {artifacts.map((a) => (
                    <li key={a.id} className="flex items-center justify-between text-sm">
                      <button className="truncate text-left underline decoration-dotted underline-offset-4 hover:text-slate-900" onClick={() => openArtifact(a)}>
                        {nameFromRepoPath(a.repo_path)}
                      </button>
                      <HStack>
                        <Button onClick={() => downloadUrl(`/api/artifact/${a.id}`)} title="Download"><UploadCloud className="h-4 w-4" /></Button>
                      </HStack>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>

        {/* Artefakt-Viewer + Feedback */}
        {selectedArtifact && (
          <Card className="mt-2">
            <HStack className="justify-between">
              <div className="font-medium">
                {nameFromRepoPath(selectedArtifact.repo_path)}{' '}
                <span className="text-xs text-slate-500">({selectedArtifact.media_type || 'datei'})</span>
              </div>
              <Button onClick={() => setSelectedArtifact(null)}>Schließen</Button>
            </HStack>
            {artifactText ? (
              <pre className="mt-2 max-h-[380px] overflow-auto rounded bg-slate-50 p-3 text-xs leading-relaxed">{artifactText}</pre>
            ) : (
              <div className="mt-2 text-sm text-slate-500">
                Nicht‑textuelles Artefakt – <button className="underline" onClick={() => downloadUrl(`/api/artifact/${selectedArtifact.id}`)}>hier öffnen</button>.
              </div>
            )}
            <div className="mt-3">
              <div className="mb-1 text-sm font-medium">Feedback</div>
              <TextArea rows={4} placeholder="Konkret und umsetzbar, z. B. 'Abschnitt X: bitte Use‑Case Y ergänzen…'" value={feedback} onChange={(e) => setFeedback(e.target.value)} />
              <HStack className="justify-end mt-2"><Button onClick={sendFeedback} disabled={!feedback.trim()}>Senden</Button></HStack>
            </div>
          </Card>
        )}
      </VStack>
    </div>
  );
}
