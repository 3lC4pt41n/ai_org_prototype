import { create } from "zustand";
import { api, getJson } from "../lib/api";

interface Purpose {
  id: string;
  name: string;
}

interface Task {
  id: string;
  name: string;
  status: string;
}

interface GraphNode {
  id: string;
  data: {
    label: string;
    status?: string;
  };
  position: {
    x: number;
    y: number;
  };
  style?: { [key: string]: string };
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
}

interface Artifact {
  id: string;
  repo_path: string;
  url?: string;
  created_at: string;
  media_type: string;
  task_id: string;
  task_desc?: string;
}

interface Feedback {
  id: string;
  user: string;
  content: string;
  timestamp: string;
}

interface PipelineState {
  purposes: Purpose[];
  selectedPurposeId: string | null;
  backlog: Task[];
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
  tasksStatus: Record<string, string>;
  artifacts: Artifact[];
  selectedArtifactId: string | null;
  artifactContent: string;
  feedbacks: Feedback[];
  isLoading: boolean;
  paused: boolean;
  error: unknown | null;
  setSelectedPurpose: (id: string) => void;
  fetchPurposes: () => Promise<void>;
  fetchBacklog: () => Promise<void>;
  fetchGraphAndStatus: (purposeId: string) => Promise<void>;
  fetchArtifacts: () => Promise<void>;
  selectArtifact: (id: string) => void;
  fetchArtifactContent: (artifactId: string) => Promise<void>;
  fetchFeedbacks: (artifactId: string) => Promise<void>;
  postFeedback: (artifactId: string, content: string) => Promise<void>;
  updateArtifact: (artifactId: string, content: string) => Promise<void>;
  pausePurpose: (purposeId: string) => Promise<void>;
  startPurpose: (purposeId: string) => Promise<void>;
  pauseAll: () => Promise<void>;
  startAll: () => Promise<void>;
}

const usePipelineStore = create<PipelineState>((set, get) => ({
  purposes: [],
  selectedPurposeId: null,
  backlog: [],
  graphNodes: [],
  graphEdges: [],
  tasksStatus: {},
  artifacts: [],
  selectedArtifactId: null,
  artifactContent: "",
  feedbacks: [],
  isLoading: false,
  paused: false,
  error: null,

  setSelectedPurpose: (id: string) => {
    set({
      selectedPurposeId: id,
      selectedArtifactId: null,
      artifactContent: "",
      feedbacks: [],
    });
  },

  fetchPurposes: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await getJson<Purpose[]>(`/purposes`);
      const list = Array.isArray(data) ? data : [];
      const current = get().selectedPurposeId;
      const next = !current && list.length > 0 ? list[0].id : current;
      set({ purposes: list, selectedPurposeId: next ?? null, isLoading: false });
    } catch (err) {
      console.error('fetchPurposes failed', err);
      set({ error: err, purposes: [], isLoading: false });
    }
  },

  fetchBacklog: async (signal?: AbortSignal) => {
    const selected = get().selectedPurposeId;
    if (!selected) return;
    try {
      const data = await getJson<Task[]>(`/backlog?purpose_id=${encodeURIComponent(selected)}`, { signal });
      set({ backlog: Array.isArray(data) ? data : [] });
    } catch (err) {
      console.error('fetchBacklog failed', err);
      set({ backlog: [], error: err });
    }
  },

  fetchGraphAndStatus: async (purposeId: string, signal?: AbortSignal) => {
    try {
      const [graphRes, statusRes] = await Promise.all([
        api.get(`/purposes/${purposeId}/graph`, { signal }),
        api.get(`/purposes/${purposeId}/status`, { signal }),
      ]);
      if (graphRes.status !== 200 || statusRes.status !== 200) {
        throw new Error(
          `API not ok: graph=${graphRes.status} status=${statusRes.status}`
        );
      }
      const { tasks, dependencies } = graphRes.data;
      const statusObj = statusRes.data;

      const nodes: GraphNode[] = Array.isArray(tasks)
        ? tasks.map((t: any, idx: number) => ({
            id: t.id,
            data: { label: t.description || t.name || t.id, status: t.status },
            position: { x: idx * 200, y: 0 },
            style: {
              borderColor:
                t.status === "done"
                  ? "#16a34a"
                  : t.status === "doing"
                  ? "#f59e0b"
                  : "#cbd5e1",
            },
          }))
        : [];

      const edges: GraphEdge[] = Array.isArray(dependencies)
        ? dependencies.map((edge: any) => ({
            id: `${edge.from_id}-${edge.to_id}`,
            source: edge.from_id,
            target: edge.to_id,
          }))
        : [];

      const taskStatus: Record<string, string> = Array.isArray(tasks)
        ? tasks.reduce((acc: any, t: any) => ({ ...acc, [t.id]: t.status }), {})
        : {};

      set({
        graphNodes: nodes,
        graphEdges: edges,
        tasksStatus: taskStatus,
        paused: Boolean(statusObj?.paused),
        error: null,
      });
    } catch (err) {
      console.error('fetchGraphAndStatus failed', err);
      set({ graphNodes: [], graphEdges: [], tasksStatus: {}, paused: false, error: err });
    }
  },

  fetchArtifacts: async (signal?: AbortSignal) => {
    const selected = get().selectedPurposeId;
    if (!selected) return;
    try {
      const data = await getJson<Artifact[]>(`/artifacts?purpose_id=${encodeURIComponent(selected)}`, { signal });
      set({ artifacts: Array.isArray(data) ? data : [] });
    } catch (err) {
      console.error('fetchArtifacts failed', err);
      set({ artifacts: [], error: err });
    }
  },

  selectArtifact: (id: string) => {
    set({ selectedArtifactId: id, artifactContent: "", feedbacks: [] });
    get().fetchArtifactContent(id);
    get().fetchFeedbacks(id);
  },

  fetchArtifactContent: async (artifactId: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.get(`/artifact/${artifactId}`);
      set({ artifactContent: res.data.content });
    } catch (err) {
      console.error('fetchArtifactContent failed', err);
      set({ artifactContent: '', error: err });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchFeedbacks: async (artifactId: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.get(`/artifacts/${artifactId}/feedback`);
      set({ feedbacks: res.data });
    } catch (err) {
      console.error('fetchFeedbacks failed', err);
      set({ feedbacks: [], error: err });
    } finally {
      set({ isLoading: false });
    }
  },

  postFeedback: async (artifactId: string, content: string) => {
    set({ isLoading: true, error: null });
    try {
      await api.post(`/artifacts/${artifactId}/feedback`, { content });
      get().fetchFeedbacks(artifactId);
    } catch (err) {
      console.error('postFeedback failed', err);
      set({ error: err });
    } finally {
      set({ isLoading: false });
    }
  },

  updateArtifact: async (artifactId: string, content: string) => {
    set({ isLoading: true, error: null });
    try {
      await api.put(`/artifact/${artifactId}`, { content });
    } catch (err) {
      console.error('updateArtifact failed', err);
      set({ error: err });
    } finally {
      set({ isLoading: false });
    }
  },

  pausePurpose: async (purposeId: string) => {
    try {
      await api.post(`/purposes/${purposeId}/pause`);
      set({ paused: true });
    } catch (err) {
      console.error('pausePurpose failed', err);
      set({ error: err });
    }
  },

  startPurpose: async (purposeId: string) => {
    try {
      await api.post(`/purposes/${purposeId}/start`);
      set({ paused: false });
    } catch (err) {
      console.error('startPurpose failed', err);
      set({ error: err });
    }
  },

  pauseAll: async () => {
    const { purposes } = get();
    for (const p of purposes) {
      try {
        await api.post(`/purposes/${p.id}/pause`);
      } catch (err) {
        console.error(`Error pausing purpose ${p.id}:`, err);
      }
    }
  },

  startAll: async () => {
    const { purposes } = get();
    for (const p of purposes) {
      try {
        await api.post(`/purposes/${p.id}/start`);
      } catch (err) {
        console.error(`Error starting purpose ${p.id}:`, err);
      }
    }
  },
}));

export default usePipelineStore;
