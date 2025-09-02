import { create } from "zustand";
import api from "../lib/api";

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
  name: string;
  content?: string;
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
  resumePurpose: (purposeId: string) => Promise<void>;
  pauseAll: () => Promise<void>;
  resumeAll: () => Promise<void>;
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
  error: null,

  setSelectedPurpose: (id: string) => {
    set({ selectedPurposeId: id });
    get().fetchGraphAndStatus(id);
    get().fetchBacklog();
    get().fetchArtifacts();
    set({ selectedArtifactId: null, artifactContent: "", feedbacks: [] });
  },

  fetchPurposes: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.get("/purposes");
      set({ purposes: Array.isArray(res.data) ? res.data : [] });
    } catch (err) {
      console.error("Error fetching purposes:", err);
      set({ error: String(err), purposes: [] });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchBacklog: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.get("/backlog");
      const selected = get().selectedPurposeId;
      const tasks: Task[] = Array.isArray(res.data) ? res.data : [];
      set({ backlog: selected ? tasks.filter((t) => t.id.startsWith(selected)) : tasks });
    } catch (err) {
      console.error("Error fetching backlog:", err);
      set({ backlog: [], error: String(err) });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchGraphAndStatus: async (purposeId: string) => {
    set({ isLoading: true, error: null });
    try {
      const [graphRes, statusRes] = await Promise.all([
        api.get(`/purposes/${purposeId}/graph`),
        api.get(`/purposes/${purposeId}/status`),
      ]);
      if (graphRes.status !== 200 || statusRes.status !== 200) {
        throw new Error(
          `API not ok: graph=${graphRes.status} status=${statusRes.status}`
        );
      }
      const graph = graphRes.data;
      const status = statusRes.data;

      const nodes: GraphNode[] = Array.isArray(graph?.nodes)
        ? graph.nodes.map((node: any, idx: number) => ({
            id: node.id,
            data: {
              label: node.name || node.id,
              status: status?.[node.id],
            },
            position: { x: idx * 200, y: 0 },
            style: {
              borderColor:
                status?.[node.id] === "done"
                  ? "#16a34a"
                  : status?.[node.id] === "doing"
                  ? "#f59e0b"
                  : "#cbd5e1",
            },
          }))
        : [];
      const edges: GraphEdge[] = Array.isArray(graph?.edges)
        ? graph.edges.map((edge: any) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
          }))
        : [];
      set({
        graphNodes: nodes,
        graphEdges: edges,
        tasksStatus: status ?? {},
        isLoading: false,
        error: null,
      });
    } catch (err) {
      console.error("fetchGraphAndStatus failed", err);
      set({ graphNodes: [], graphEdges: [], tasksStatus: {}, error: String(err) });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchArtifacts: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.get("/artifacts");
      const arts: Artifact[] = Array.isArray(res.data) ? res.data : [];
      const selected = get().selectedPurposeId;
      set({ artifacts: selected ? arts.filter((a) => a.id.startsWith(selected)) : arts });
    } catch (err) {
      console.error("Error fetching artifacts:", err);
      set({ artifacts: [], error: String(err) });
    } finally {
      set({ isLoading: false });
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
      console.error("Error fetching artifact content:", err);
      set({ error: err });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchFeedbacks: async (artifactId: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await api.get(`/feedback/${artifactId}`);
      set({ feedbacks: res.data });
    } catch (err) {
      console.error("Error fetching feedbacks:", err);
      set({ error: err });
    } finally {
      set({ isLoading: false });
    }
  },

  postFeedback: async (artifactId: string, content: string) => {
    set({ isLoading: true, error: null });
    try {
      await api.post(`/feedback/${artifactId}`, { content });
      get().fetchFeedbacks(artifactId);
    } catch (err) {
      console.error("Error posting feedback:", err);
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
      console.error("Error updating artifact:", err);
      set({ error: err });
    } finally {
      set({ isLoading: false });
    }
  },

  pausePurpose: async (purposeId: string) => {
    try {
      await api.post(`/purposes/${purposeId}/pause`);
    } catch (err) {
      console.error("Error pausing purpose:", err);
    }
  },

  resumePurpose: async (purposeId: string) => {
    try {
      await api.post(`/purposes/${purposeId}/resume`);
    } catch (err) {
      console.error("Error resuming purpose:", err);
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

  resumeAll: async () => {
    const { purposes } = get();
    for (const p of purposes) {
      try {
        await api.post(`/purposes/${p.id}/resume`);
      } catch (err) {
        console.error(`Error resuming purpose ${p.id}:`, err);
      }
    }
  },
}));

export default usePipelineStore;
