import { api } from '../lib/api';

export interface ArtifactSummary {
  id: string;
  name?: string | null;
  path?: string | null;
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
  const resp = await api.get<ArtifactDetails | null>(`/artifact/${artifactId}`);
  return resp.data ?? null;
}

export async function getFeedbackForArtifact(artifactId: string): Promise<ArtifactFeedbackMessage[]> {
  const resp = await api.get<{ messages?: ArtifactFeedbackMessage[] } | ArtifactFeedbackMessage[]>(
    `/artifacts/${artifactId}/feedback`,
  );
  const normalize = (items: ArtifactFeedbackMessage[]): ArtifactFeedbackMessage[] =>
    items.map((msg) => ({ ...msg, id: msg.id ?? null }));
  if (resp.data && Array.isArray(resp.data.messages)) {
    return normalize(resp.data.messages);
  }
  if (Array.isArray(resp.data)) {
    return normalize(resp.data);
  }
  return [];
}

export async function postFeedbackForArtifact(
  artifactId: string,
  message: string,
  intent: string = 'feedback',
): Promise<void> {
  await api.post(`/artifacts/${artifactId}/feedback`, { message, intent, role: 'user' });
}
