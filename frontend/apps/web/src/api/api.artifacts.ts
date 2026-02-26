import { api } from '../lib/api';

export interface ArtifactSummary {
  id: string;
  name?: string | null;
  path?: string | null;
  url?: string | null;
  media_type?: string | null;
  created_at?: string | null;
  createdAt?: string | null;
  released?: boolean;
  [key: string]: unknown;
}

export interface ArtifactDetails extends ArtifactSummary {
  content?: string | null;
  text?: string | null;
  markdown?: string | null;
}

export interface ArtifactFeedbackMessage {
  id: string | null;
  role?: string | null;
  author?: string | null;
  intent?: string | null;
  created_at?: string | null;
  createdAt?: string | null;
  content?: string | null;
  text?: string | null;
  markdown?: string | null;
  [key: string]: unknown;
}

export async function listArtifactsByPurpose(purposeId: string): Promise<ArtifactSummary[]> {
  const resp = await api.get<ArtifactSummary[]>(`/artifacts?purpose_id=${encodeURIComponent(purposeId)}`);
  return Array.isArray(resp.data) ? resp.data : [];
}

export async function getArtifactById(artifactId: string): Promise<ArtifactDetails | null> {
  const resp = await api.get(`/artifact/${artifactId}`, {
    responseType: 'text',
    transformResponse: [(data: unknown) => data],
  });
  const raw = resp.data;
  // The backend returns a FileResponse (raw text), not a JSON object.
  // Wrap the text content into an ArtifactDetails shape for callers.
  if (typeof raw === 'string') {
    return { id: artifactId, content: raw, text: raw, markdown: raw };
  }
  // Fallback: if the response was somehow parsed as JSON, return as-is
  return (raw as ArtifactDetails) ?? null;
}

