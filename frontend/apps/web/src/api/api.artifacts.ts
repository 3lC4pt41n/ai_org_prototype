import axios from 'axios';

export interface ArtifactSummary {
  id: string;
  name?: string | null;
  path?: string | null;
  created_at?: string | null;
  createdAt?: string | null;
}

export interface ArtifactDetails extends ArtifactSummary {
  content?: string | null;
  text?: string | null;
  markdown?: string | null;
}

export interface ArtifactFeedbackMessage {
  id?: string;
  role?: string | null;
  content?: string | null;
  text?: string | null;
  created_at?: string | null;
  createdAt?: string | null;
}

export interface ArtifactFeedbackResponse {
  messages?: ArtifactFeedbackMessage[];
}

export async function listArtifactsByPurpose(
  purposeId: string,
): Promise<ArtifactSummary[]> {
  const { data } = await axios.get<ArtifactSummary[]>(
    '/api/artifacts',
    { params: { purpose_id: purposeId } },
  );
  return Array.isArray(data) ? data : [];
}

export async function getArtifactById(
  artifactId: string,
): Promise<ArtifactDetails | null> {
  try {
    const { data } = await axios.get<ArtifactDetails>(
      `/api/artifact/${artifactId}`,
    );
    return data ?? null;
  } catch (primaryError) {
    try {
      const { data } = await axios.get<ArtifactSummary[]>(
        '/api/artifacts',
      );
      if (Array.isArray(data)) {
        return (data.find((entry) => entry.id === artifactId) ?? null) as ArtifactDetails | null;
      }
    } catch (fallbackError) {
      console.error('Artifact fallback fetch failed', fallbackError);
    }
    throw primaryError;
  }
}

export async function getFeedbackForArtifact(
  artifactId: string,
): Promise<ArtifactFeedbackResponse> {
  const { data } = await axios.get<ArtifactFeedbackResponse>(
    `/api/artifacts/${artifactId}/feedback`,
  );
  return data ?? { messages: [] };
}

export async function postFeedbackForArtifact(
  artifactId: string,
  message: string,
): Promise<ArtifactFeedbackResponse> {
  const { data } = await axios.post<ArtifactFeedbackResponse>(
    `/api/artifacts/${artifactId}/feedback`,
    { message, role: 'user', intent: 'feedback' },
  );
  return data ?? { messages: [] };
}
