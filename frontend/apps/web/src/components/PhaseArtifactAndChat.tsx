import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import {
  listArtifactsByPurpose,
  getArtifactById,
  getFeedbackForArtifact,
  postFeedbackForArtifact,
  type ArtifactDetails,
  type ArtifactFeedbackMessage,
} from '../api/api.artifacts';

type PhaseArtifactAndChatProps = {
  purposeId: string;
  phaseKey?: string;
};

export default function PhaseArtifactAndChat({ purposeId, phaseKey }: PhaseArtifactAndChatProps) {
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<ArtifactDetails | null>(null);
  const [messages, setMessages] = useState<ArtifactFeedbackMessage[]>([]);
  const [input, setInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingArtifact, setIsLoadingArtifact] = useState(false);
  const [isLoadingFeedback, setIsLoadingFeedback] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  // Wähle automatisch das relevante Artefakt der Phase (oder neuestes als Fallback)
  useEffect(() => {
    let canceled = false;
    setIsLoadingArtifact(true);
    setIsLoadingFeedback(true);
    async function selectArtifact() {
      try {
        const list = await listArtifactsByPurpose(purposeId);
        if (canceled) return;
        if (!list.length) {
          setArtifactId(null);
          setIsLoadingArtifact(false);
          setIsLoadingFeedback(false);
          return;
        }
        const toTimestamp = (value?: string | null) => {
          if (!value) return -Infinity;
          const ts = new Date(value).getTime();
          return Number.isNaN(ts) ? -Infinity : ts;
        };
        const sorted = [...list].sort((a, b) => toTimestamp(a.created_at ?? a.createdAt) - toTimestamp(b.created_at ?? b.createdAt));
        // Finde Artefakt mit passendem Namen zum Phasenschlüssel
        let best = sorted[sorted.length - 1];
        if (phaseKey) {
          const phaseNeedle = phaseKey.toLowerCase();
          const match = sorted.find(a => (a.name || a.path || '').toLowerCase().includes(phaseNeedle));
          if (match) best = match;
        }
        setArtifactId((prev) => {
          if (prev === best.id) {
            setIsLoadingArtifact(false);
            setIsLoadingFeedback(false);
            return prev;
          }
          return best.id;
        });
      } catch (error) {
        console.error('Unable to select artifact', error);
        if (!canceled) {
          setArtifactId(null);
          setIsLoadingArtifact(false);
          setIsLoadingFeedback(false);
        }
      }
    }
    selectArtifact();
    return () => { canceled = true; };
  }, [purposeId, phaseKey]);

  // Lade Artefakt-Details und zugehörige Chat-Verlauf
  useEffect(() => {
    if (!artifactId) {
      setArtifact(null);
      setMessages([]);
      setIsLoadingArtifact(false);
      setIsLoadingFeedback(false);
      return;
    }
    let canceled = false;
    setIsLoadingArtifact(true);
    setIsLoadingFeedback(true);
    async function loadArtifactAndFeedback() {
      try {
        const [artifactDetails, feedback] = await Promise.all([
          getArtifactById(artifactId),
          getFeedbackForArtifact(artifactId),
        ]);
        if (canceled) return;
        setArtifact(artifactDetails);
        setMessages(feedback);
      } catch (error) {
        console.error('Fehler beim Laden des Artefakts oder Feedbacks', error);
        if (!canceled) {
          setArtifact(null);
          setMessages([]);
        }
      } finally {
        if (!canceled) {
          setIsLoadingArtifact(false);
          setIsLoadingFeedback(false);
        }
      }
    }
    loadArtifactAndFeedback();
    return () => { canceled = true; };
  }, [artifactId]);

  // Automatisch ans Ende scrollen, wenn neue Nachrichten eintreffen
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  async function handleSend() {
    const text = input.trim();
    if (!text || !artifactId) return;
    setIsSubmitting(true);
    const optimisticId = `temp-${Date.now()}`;
    const optimisticMessage: ArtifactFeedbackMessage = {
      id: optimisticId,
      intent: 'feedback',
      content: text,
      created_at: new Date().toISOString(),
      role: 'user',
    };
    setMessages((prev) => [...prev, optimisticMessage]);
    try {
      setInput('');
      setIsLoadingFeedback(true);
      await postFeedbackForArtifact(artifactId, text);
      const [feedback, updatedArtifact] = await Promise.all([
        getFeedbackForArtifact(artifactId),
        getArtifactById(artifactId),
      ]);
      setMessages(feedback);
      setArtifact(prev => updatedArtifact ?? prev);
    } catch (error) {
      console.error('Fehler beim Senden der Rückmeldung', error);
      setMessages((prev) => prev.filter((msg) => msg.id !== optimisticId));
      setInput(text);
    } finally {
      setIsSubmitting(false);
      setIsLoadingFeedback(false);
    }
  }

  async function handleApprove() {
    if (!artifactId) return;
    setIsSubmitting(true);
    try {
      setIsLoadingFeedback(true);
      await postFeedbackForArtifact(artifactId, 'Approved', 'approval');
      const [feedback, updatedArtifact] = await Promise.all([
        getFeedbackForArtifact(artifactId),
        getArtifactById(artifactId),
      ]);
      setMessages(feedback);
      setArtifact(prev => updatedArtifact ?? (prev ? { ...prev, released: true } : prev));
    } catch (error) {
      console.error('Fehler bei Freigabe', error);
    } finally {
      setIsSubmitting(false);
      setIsLoadingFeedback(false);
    }
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      void handleSend();
    }
  }

  const hasMessages = messages.length > 0;

  return (
    <div className="mb-6">
      {isLoadingArtifact ? (
        <p className="mb-4 text-sm text-gray-500 flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-gray-400 animate-pulse" />
          Artefakt wird geladen…
        </p>
      ) : artifact ? (
        <>
          <h2 className="text-base font-semibold mb-2">
            {artifact.name || artifact.path || 'Artefakt'}
          </h2>
          {(artifact.content || artifact.text || artifact.markdown) ? (
            <pre className="mb-4 p-3 border rounded bg-gray-50 overflow-x-auto whitespace-pre-wrap">
              {artifact.content || artifact.text || artifact.markdown}
            </pre>
          ) : (
            <p className="mb-4 italic text-sm text-gray-500">Kein Artefakt-Inhalt verfügbar.</p>
          )}
        </>
      ) : (
        <p className="mb-4 text-sm text-gray-500">Kein Artefakt verfügbar.</p>
      )}

      {artifact && (
        <div className="mb-4">
          <div className="mb-1 flex items-center justify-between text-xs text-gray-500">
            <span>Chat-Verlauf</span>
            {isLoadingFeedback && (
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-gray-400 animate-pulse" />
                Lädt…
              </span>
            )}
          </div>
          <div className="p-3 border rounded bg-white max-h-60 overflow-y-auto">
            {hasMessages ? (
              messages.map((msg, idx) => {
                const timestamp = msg.created_at ?? msg.createdAt ?? null;
                const body = msg.content ?? msg.text ?? msg.markdown ?? '';
                return (
                  <div key={msg.id ?? `msg-${idx}`} className="mb-2 last:mb-0">
                    <div className="text-xs text-gray-600 mb-1">
                      {msg.intent === 'question' ? '[Frage]' : msg.intent === 'approval' ? '[Freigabe]' : '[Feedback]'}
                      {timestamp && (
                        <> – {new Date(timestamp).toLocaleString('de-DE')}</>
                      )}
                    </div>
                    <div className="whitespace-pre-wrap text-sm">
                      {body || <span className="italic text-gray-500">(kein Inhalt)</span>}
                    </div>
                  </div>
                );
              })
            ) : isLoadingFeedback ? (
              <p className="text-sm text-gray-500">Nachrichten werden geladen…</p>
            ) : (
              <p className="text-sm text-gray-500">Noch keine Nachrichten für diese Phase.</p>
            )}
            <div ref={endRef} />
          </div>
        </div>
      )}

      {artifact && !artifact.released && (
        <div className="p-3 border rounded bg-white">
          <label className="block text-sm font-medium mb-1">Feedback / Rückfrage</label>
          <textarea
            rows={3}
            className="w-full p-2 border rounded text-sm"
            placeholder="Schreibe eine Rückmeldung oder Frage zur Phase…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleInputKeyDown}
          />
          <div className="mt-2 flex gap-2">
            <button
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
              onClick={handleSend}
              disabled={isSubmitting || !input.trim()}
            >
              Senden
            </button>
            <button
              className="px-3 py-1 bg-green-600 text-white rounded text-sm disabled:opacity-50"
              onClick={handleApprove}
              disabled={isSubmitting}
            >
              Freigeben
            </button>
          </div>
        </div>
      )}

      {artifact?.released && (
        <p className="p-3 mt-2 border rounded bg-green-50 text-green-700 text-sm">Phase wurde freigegeben.</p>
      )}
    </div>
  );
}
