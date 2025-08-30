import React, { useEffect, useState } from 'react';
import PurposeInput from '../components/pipeline/PurposeInput';
import StatusIndicator from '../components/pipeline/StatusIndicator';
import FeedbackForm from '../components/pipeline/FeedbackForm';
import Accordion from '../components/ui/Accordion';
import ReactFlow, { MiniMap, Controls, Background } from 'reactflow';
import 'reactflow/dist/style.css';
import { Gauge } from 'lucide-react';
import { getJson, postJson, API_BASE } from '@api';
import { toast } from 'react-hot-toast';

const API = API_BASE;
const headers = {
  Accept: 'application/json',
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
};

export default function PipelinePage() {
  const [purpose, setPurpose] = useState('');
  const [purposeId, setPurposeId] = useState<string>();
  const [prd, setPrd] = useState('');
  const [blueprint, setBlueprint] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'complete'>('idle');
  const [counts, setCounts] = useState({ todo: 0, doing: 0, done: 0 });
  const [paused, setPaused] = useState(false);
  const [feedbackPrd, setFeedbackPrd] = useState('');
  const [feedbackArch, setFeedbackArch] = useState('');
  const [historyPrd, setHistoryPrd] = useState<any[]>([]);
  const [historyArch, setHistoryArch] = useState<any[]>([]);
  const approvedPrd = historyPrd.some((h) => h.approved);
  const approvedArch = historyArch.some((h) => h.approved);
  const [budget, setBudget] = useState<number | null>(null);
  const [budgetTotal, setBudgetTotal] = useState<number | null>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [elements, setElements] = useState<any[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);

  function statusColor(status: string) {
    switch (status) {
      case 'done':
        return '#22c55e';
      case 'doing':
        return '#fbbf24';
      case 'failed':
        return '#ef4444';
      default:
        return '#64748b';
    }
  }

  function getNodeSize(task: any) {
    const base = 40;
    const max = 140;
    const bv = task.business_value ?? 1;
    const scale = Math.log2(bv + 1) * 25 + base;
    return Math.max(base, Math.min(scale, max));
  }

  // Create a new purpose and start the pipeline
  async function start() {
    setStatus('loading');
    try {
      const data = await createPurpose(purpose);
      setPrd(data.requirements ?? '');
      setBlueprint(data.blueprint ?? '');
      setPurposeId(data.purpose_id);
      setFeedbackPrd('');
      setFeedbackArch('');
      setStatus('ready');
      loadHistory(data.purpose_id);
      loadStatus(data.purpose_id);
    } catch (e: any) {
      toast.error(e.message || 'Failed to start pipeline');
      setStatus('idle');
    }
  }

  // Load feedback history
  async function loadHistory(pid: string) {
    const data = await getJson(`/purpose/${pid}/feedback`);
    const prdHistory = data.filter((e: any) => e.type === 'prd');
    const archHistory = data.filter((e: any) => e.type === 'blueprint');
    setHistoryPrd(prdHistory);
    setHistoryArch(archHistory);
  }

  // Load pipeline status, tasks and artifacts
  async function loadStatus(pid: string) {
    const [statusData, graphData, artifactsData] = await Promise.all([
      fetch(`${API}/purpose/${pid}/status`, { headers }).then((r) => r.json()),
      fetch(`${API}/purpose/${pid}/graph`, { headers }).then((r) => r.json()),
      getJson(`/artifacts?purpose_id=${pid}`),
    ]);
    setPaused(statusData.paused);
    setBudget(statusData.budget_left);
    setBudgetTotal(statusData.budget_total);
    const tasksList: any[] = graphData.tasks || [];
    const done = tasksList.filter((t) => t.status === 'done').length;
    const doing = tasksList.filter((t) => t.status === 'doing').length;
    const todo = tasksList.filter((t) => t.status === 'todo').length;
    setCounts({ done, doing, todo });
    setTasks(tasksList);
    const nodes = tasksList.map((task) => ({
      id: task.id,
      data: {
        label: (
          <div style={{ textAlign: 'center' }}>
            <b>{task.description.slice(0, 32)}…</b>
            <div style={{ fontSize: 12, opacity: 0.8, marginTop: 4 }}>
              💸 BV: <b>{task.business_value}</b>
              <br />
              📊 Token Plan/Ist: <b>{task.tokens_plan ?? '-'}</b> /{' '}
              <b>{task.tokens_actual ?? '-'}</b>
              <br />
              <i>Status: {task.status}</i>
            </div>
          </div>
        ),
      },
      position: { x: Math.random() * 600, y: Math.random() * 600 },
      style: {
        border: `3px solid ${statusColor(task.status)}`,
        background: '#1e293b',
        color: '#fff',
        width: getNodeSize(task),
        height: getNodeSize(task),
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 0 8px #0ff5',
        fontSize: 15,
        fontWeight: 500,
      },
    }));
    const edges = (graphData.dependencies || []).map((dep: any) => ({
      id: `${dep.from_id}->${dep.to_id}`,
      source: dep.from_id,
      target: dep.to_id,
    }));
    setElements([...nodes, ...edges]);
    setArtifacts(artifactsData);
  }

  // Pause or resume the purpose
  async function togglePause() {
    if (!purposeId) return;
    const endpoint = paused ? `/purpose/${purposeId}/resume` : `/purpose/${purposeId}/pause`;
    await fetch(`${API}${endpoint}`, { method: 'POST', headers });
    setPaused(!paused);
  }

  // Send feedback or approval for PRD or architecture
  async function sendFeedback(type: 'prd' | 'blueprint') {
    if (!purposeId) return;
    const text = type === 'prd' ? feedbackPrd : feedbackArch;
    try {
      const data = await postJson(`/purpose/${purposeId}/feedback`, {
        type,
        text,
      });
      if (type === 'prd') {
        if (data.prdContent) setPrd(data.prdContent);
        setFeedbackPrd('');
      } else {
        if (data.blueprintContent) setBlueprint(data.blueprintContent);
        setFeedbackArch('');
      }
      loadHistory(purposeId);
      setStatus('ready');
    } catch (e: any) {
      toast.error(e.message || 'Failed to send feedback');
    }
  }

  async function approve(type: 'prd' | 'blueprint') {
    if (!purposeId) return;
    try {
      await postJson(`/purpose/${purposeId}/feedback`, { type, approved: true });
      loadHistory(purposeId);
      if (type === 'prd') {
        setStatus(approvedArch ? 'complete' : 'ready');
      } else {
        setStatus(approvedPrd ? 'complete' : 'ready');
      }
    } catch (e: any) {
      toast.error(e.message || 'Failed to approve');
    }
  }

  useEffect(() => {
    if (approvedPrd && approvedArch) {
      setStatus('complete');
    }
  }, [approvedPrd, approvedArch]);

  // Poll budget before a purpose is started
  useEffect(() => {
    if (purposeId) return;
    const tick = () =>
      getJson('/')
        .then((d) => {
          setBudget(d.budget_left);
          setBudgetTotal(d.budget_total);
        })
        .catch(() => {});
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, [purposeId]);

  useEffect(() => {
    if (!purposeId) return;
    const id = setInterval(() => loadStatus(purposeId), 5000);
    return () => clearInterval(id);
  }, [purposeId]);

  return (
    <div className="p-8 bg-white text-gray-900 space-y-6">
      <div className="max-w-md">
        <div className="flex items-center gap-2">
          <Gauge className="text-emerald-400" />
          <div>
            <p className="text-sm">Budget left (USD)</p>
            <p className="text-2xl font-bold">
              {budget !== null ? budget.toFixed(2) : '…'}{' '}
              <span className="text-base font-normal">/ {budgetTotal?.toFixed(2) ?? '…'} USD</span>
            </p>
          </div>
        </div>
        {budgetTotal != null && budget != null && (
          <div className="w-full bg-slate-200 rounded h-3 mt-1">
            <div
              className={
                'h-3 rounded ' +
                (budget / budgetTotal <= 0
                  ? 'bg-red-600 animate-pulse'
                  : budget / budgetTotal <= 0.1
                    ? 'bg-red-500'
                    : budget / budgetTotal <= 0.25
                      ? 'bg-yellow-500'
                      : 'bg-emerald-500')
              }
              style={{ width: `${(100 * (budgetTotal - budget)) / budgetTotal}%` }}
            />
          </div>
        )}
      </div>

      <Accordion title="🚀 Projektziel" defaultOpen={!purposeId}>
        {!purposeId ? (
          <PurposeInput value={purpose} onChange={setPurpose} onStart={start} />
        ) : (
          <div className="flex justify-between items-center text-sm">
            <span className="text-gray-600">
              Purpose ID: <span className="font-mono">{purposeId}</span>
            </span>
            <div className="flex items-center gap-2">
              <div className="flex gap-2">
                <span className="px-2 py-0.5 rounded bg-green-500 text-white text-xs">
                  Done {counts.done}
                </span>
                <span className="px-2 py-0.5 rounded bg-blue-500 text-white text-xs">
                  Doing {counts.doing}
                </span>
                <span className="px-2 py-0.5 rounded bg-gray-500 text-white text-xs">
                  Todo {counts.todo}
                </span>
              </div>
              <button
                className={`px-3 py-1 rounded text-white hover:opacity-90 ${
                  paused ? 'bg-emerald-600' : 'bg-red-600'
                }`}
                onClick={togglePause}
              >
                {paused ? 'Fortsetzen' : 'Pause'}
              </button>
            </div>
          </div>
        )}
      </Accordion>

      <StatusIndicator status={status} />

      {prd && (
        <Accordion title="📄 PRD" defaultOpen>
          <pre className="text-sm whitespace-pre-wrap overflow-auto max-h-96">{prd}</pre>
          <FeedbackForm
            value={feedbackPrd}
            onChange={setFeedbackPrd}
            onSend={() => sendFeedback('prd')}
            onApprove={() => approve('prd')}
            history={historyPrd}
            disabled={approvedPrd}
          />
        </Accordion>
      )}

      {blueprint && (
        <Accordion title="📐 Architektur" defaultOpen>
          <pre className="text-sm whitespace-pre-wrap overflow-auto max-h-96">{blueprint}</pre>
          <FeedbackForm
            value={feedbackArch}
            onChange={setFeedbackArch}
            onSend={() => sendFeedback('blueprint')}
            onApprove={() => approve('blueprint')}
            history={historyArch}
            disabled={approvedArch}
          />
        </Accordion>
      )}

      {tasks.length > 0 && (
        <Accordion title="🗺️ Tasks">
          <div
            style={{
              width: '100%',
              height: 400,
              background: '#f5f5f5',
              borderRadius: 8,
              boxShadow: '0 8px 32px #000a',
            }}
          >
            {elements.length === 0 ? (
              <p className="text-center pt-8">No tasks to display</p>
            ) : (
              <ReactFlow elements={elements} fitView>
                <MiniMap
                  nodeStrokeColor={(n) => (n.style?.border as string) ?? '#94a3b8'}
                  nodeColor={(n) => (n.style?.background as string) ?? '#cbd5e1'}
                />
                <Controls />
                <Background color="#cbd5e1" gap={18} />
              </ReactFlow>
            )}
          </div>
        </Accordion>
      )}

      {purposeId && (
        <Accordion title="📦 Artefakte">
          <ul className="space-y-1 text-sm">
            {artifacts.map((a) => (
              <li key={a.id} className="border-b border-slate-200 py-1">
                <span className="text-amber-400 font-mono mr-2">{a.task_id}</span>
                {a.repo_path}{' '}
                <span className="text-slate-600 text-xs">
                  ({a.media_type}, {new Date(a.created_at).toLocaleString()})
                </span>
              </li>
            ))}
            {artifacts.length === 0 && <li className="italic">No artifacts yet</li>}
          </ul>
        </Accordion>
      )}

      <div className="flex justify-end">
        <button className="btn btn-primary" disabled={status !== 'complete'}>
          Weiter
        </button>
      </div>
    </div>
  );
}

async function createPurpose(purpose: string) {
  const data = await postJson('/purpose', { purpose });
  return data;
}
