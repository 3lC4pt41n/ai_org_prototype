import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getArtifactById,
  getFeedbackForArtifact,
  listArtifactsByPurpose,
  postFeedbackForArtifact,
  type ArtifactDetails,
  type ArtifactFeedbackMessage,
  type ArtifactSummary,
} from '@/api/api.artifacts';

type PhaseArtifactAndChatProps = {
  purposeId: string;
  phaseKey?: string;
};

function normalizeTimestamp(value?: string | null): number {
  if (!value) return 0;
  const date = new Date(value);
  const timestamp = date.getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function isRelevantMatch(entry: ArtifactSummary | null, phaseKey?: string): number {
  if (!entry || !phaseKey) return 0;
  const haystack = `${entry.name ?? ''} ${entry.path ?? ''}`.toLowerCase();
  return haystack.includes(phaseKey.toLowerCase()) ? 1 : 0;
}

function extractMessageText(message: ArtifactFeedbackMessage): string {
  return (
    message.content ??
    message.text ??
    ''
  );
}

function extractMessageTimestamp(message: ArtifactFeedbackMessage): string | undefined {
  return message.created_at ?? message.createdAt ?? undefined;
}

export function PhaseArtifactAndChat({ purposeId, phaseKey }: PhaseArtifactAndChatProps) {
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<ArtifactDetails | null>(null);
  const [messages, setMessages] = useState<ArtifactFeedbackMessage[]>([]);
  const [input, setInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const sortedMessages = useMemo(
    () =>
      [...messages].sort(
        (a, b) => normalizeTimestamp(extractMessageTimestamp(a)) - normalizeTimestamp(extractMessageTimestamp(b)),
      ),
    [messages],
  );

  useEffect(() => {
    let cancelled = false;

    async function selectArtifact() {
      try {
        const list = await listArtifactsByPurpose(purposeId);
        if (!Array.isArray(list) || list.length === 0) return;
        const [best] = [...list].sort((a, b) => {
          const relevanceDelta = isRelevantMatch(b, phaseKey) - isRelevantMatch(a, phaseKey);
          if (relevanceDelta !== 0) return relevanceDelta;
          return normalizeTimestamp(b.created_at ?? b.createdAt) - normalizeTimestamp(a.created_at ?? a.createdAt);
        });
        if (!cancelled) {
          setArtifactId(best?.id ?? null);
        }
      } catch (error) {
        console.error('Unable to select artifact', error);
      }
    }

    selectArtifact();
    return () => {
      cancelled = true;
    };
  }, [purposeId, phaseKey]);

  useEffect(() => {
    if (!artifactId) return undefined;
    let cancelled = false;

    async function loadArtifactAndFeedback() {
      try {
        const [artifactDetails, feedback] = await Promise.all([
          getArtifactById(artifactId),
          getFeedbackForArtifact(artifactId),
        ]);
        if (!cancelled) {
          setArtifact(artifactDetails);
          setMessages(Array.isArray(feedback?.messages) ? feedback.messages : []);
        }
      } catch (error) {
        console.error('Unable to fetch artifact details', error);
        if (!cancelled) {
          setArtifact(null);
          setMessages([]);
        }
      }
    }

    loadArtifactAndFeedback();
    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  const handleSubmit = useCallback(async () => {
    const text = input.trim();
    if (!text || !artifactId || isSubmitting) return;
    setIsSubmitting(true);
    setInput('');
    try {
      await postFeedbackForArtifact(artifactId, text);
      const feedback = await getFeedbackForArtifact(artifactId);
      setMessages(Array.isArray(feedback?.messages) ? feedback.messages : []);
    } catch (error) {
      console.error('Unable to submit feedback', error);
      setInput(text);
    } finally {
      setIsSubmitting(false);
    }
  }, [artifactId, input, isSubmitting]);

  const artifactTitle = useMemo(
    () => artifact?.name ?? artifact?.path ?? 'Artefakt',
    [artifact?.name, artifact?.path],
  );

  const artifactContent = useMemo(
    () => artifact?.content ?? artifact?.text ?? artifact?.markdown ?? '',
    [artifact?.content, artifact?.text, artifact?.markdown],
  );

  return (
    <div className="grid gap-3" style={{ gridTemplateRows: 'auto 280px' }}>
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-base font-semibold text-slate-700">{artifactTitle}</h2>
        {artifactContent ? (
          <pre className="max-h-[420px] overflow-y-auto whitespace-pre-wrap font-mono text-sm text-slate-800">
            {artifactContent}
          </pre>
        ) : (
          <p className="text-sm text-slate-500">
            Dieser Server liefert keinen Inhalt. Bitte Backend-Detail-API ergänzen.
          </p>
        )}
      </div>

      <section className="flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
        <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700">
          Chat zur Architektur (automatisch mit Artefakt verknüpft)
        </header>
        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm text-slate-700">
          {sortedMessages.length === 0 ? (
            <p className="text-slate-500">Noch keine Nachrichten vorhanden.</p>
          ) : (
            sortedMessages.map((message, index) => {
              const key = message.id ?? `${index}`;
              const createdAt = extractMessageTimestamp(message);
              const label = createdAt
                ? new Date(createdAt).toLocaleString()
                : undefined;
              return (
                <article key={key} className="space-y-1">
                  <div className="text-xs font-medium text-slate-500">
                    {message.role ?? 'user'}
                    {label ? ` · ${label}` : null}
                  </div>
                  <p className="whitespace-pre-wrap text-slate-700">{extractMessageText(message)}</p>
                </article>
              );
            })
          )}
        </div>
        <footer className="flex items-center gap-2 border-t border-slate-200 px-4 py-3">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSubmit();
              }
            }}
            placeholder="Schreibe eine Nachricht…"
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            type="button"
            onClick={() => {
              void handleSubmit();
            }}
            disabled={!input.trim() || isSubmitting}
            className="inline-flex items-center rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {isSubmitting ? 'Senden…' : 'Senden'}
          </button>
        </footer>
      </section>
    </div>
  );
}

export default PhaseArtifactAndChat;
