import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../lib/api";

interface Artifact {
  id: string;
  url?: string;
}

interface FeedbackEntry {
  id: string;
  version: number;
  content: string;
  created_at?: string;
}

interface Props {
  title: string;
  artifact: Artifact;
  statusIcon: React.ReactNode;
  /** zeige Eingabe nur, wenn pausiert */
  showFeedback?: boolean;
}

export default function ArtifactSection({
  title,
  artifact,
  statusIcon,
  showFeedback = false,
}: Props) {
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [history, setHistory] = useState<FeedbackEntry[]>([]);
  const [idx, setIdx] = useState<number>(0);
  const [draft, setDraft] = useState<string>("");
  const [submitState, setSubmitState] = useState<"idle" | "ok" | "err">("idle");

  // PRD/Blueprint laden (als Text/Markdown)
  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(artifact.url ?? `/api/artifact/${artifact.id}`, {
          headers: { Authorization: `Bearer ${localStorage.getItem("token") || ""}` },
        });
        if (!res.ok) throw new Error(`artifact ${res.status}`);
        const text = await res.text();
        if (!alive) return;
        setContent(text);
      } catch (e: any) {
        if (!alive) return;
        setContent("");
        setError("Artefakt konnte nicht geladen werden.");
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [artifact.id, artifact.url]);

  // Feedback-Historie laden (neueste zuletzt)
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const r = await api.get(`/artifacts/${artifact.id}/feedback`);
        const list: FeedbackEntry[] = Array.isArray(r.data) ? r.data : [];
        if (!alive) return;
        setHistory(list);
        setIdx(list.length ? list.length - 1 : 0);
      } catch {
        if (!alive) return;
        setHistory([]);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [artifact.id]);

  async function sendFeedback() {
    if (!draft.trim()) return;
    setSubmitState("idle");
    try {
      await api.post(`/artifacts/${artifact.id}/feedback`, { content: draft.trim() });
      setDraft("");
      setSubmitState("ok");
      // neu laden
      const r = await api.get(`/artifacts/${artifact.id}/feedback`);
      const list: FeedbackEntry[] = Array.isArray(r.data) ? r.data : [];
      setHistory(list);
      setIdx(list.length ? list.length - 1 : 0);
      try {
        const res = await fetch(artifact.url ?? `/api/artifact/${artifact.id}`, {
          headers: { Authorization: `Bearer ${localStorage.getItem("token") || ""}` },
        });
        if (res.ok) {
          const text = await res.text();
          setContent(text);
        }
      } catch {
        /* ignore refresh errors */
      }
    } catch {
      setSubmitState("err");
    }
  }

  function renderFeedback(fb: FeedbackEntry | undefined) {
    if (!fb) return null;
    // Falls jemand Antworten (JSON) geschickt hat, nett darstellen – sonst plain.
    try {
      const parsed = JSON.parse(fb.content);
      if (Array.isArray(parsed)) {
        return (
          <ul className="list-disc ml-4 text-sm">
            {parsed.map((qa: any, i: number) => (
              <li key={i} className="mb-1">
                <p><b>Q:</b> {qa.question}</p>
                <p><b>A:</b> {qa.answer}</p>
              </li>
            ))}
          </ul>
        );
      }
    } catch {
      /* ignore – plain text */
    }
    return <p className="whitespace-pre-wrap text-sm">{fb.content}</p>;
  }

  return (
    <section className="mb-6 pb-6 border-b">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <span>{statusIcon}</span>
        {title}
      </h2>

      <div className="mb-3 p-3 border rounded bg-white">
        {loading ? (
          <p className="text-sm text-gray-500">Lade…</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : (
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
      </div>

      {/* Feedback-Historie */}
      {history.length > 0 && (
        <div className="mb-3 p-3 border rounded bg-white">
          <div className="flex items-center justify-between mb-2 text-sm">
            <button
              className="px-2 py-1 border rounded disabled:opacity-50"
              onClick={() => setIdx(i => Math.max(0, i - 1))}
              disabled={idx === 0}
              aria-label="vorheriges Feedback"
            >
              ◀
            </button>
            <span>
              Feedback {idx + 1} / {history.length}
            </span>
            <button
              className="px-2 py-1 border rounded disabled:opacity-50"
              onClick={() => setIdx(i => Math.min(history.length - 1, i + 1))}
              disabled={idx === history.length - 1}
              aria-label="nächstes Feedback"
            >
              ▶
            </button>
          </div>
          {renderFeedback(history[idx])}
        </div>
      )}

      {/* Eingabe (nur bei Pause) */}
      {showFeedback && (
        <div className="p-3 border rounded bg-white">
          <label className="block text-sm font-medium mb-1">Dein Feedback</label>
          <textarea
            rows={4}
            className="w-full p-2 border rounded text-sm"
            placeholder="Schreibe freies Feedback oder Rückfragen…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
              onClick={sendFeedback}
              disabled={!draft.trim()}
            >
              Feedback senden
            </button>
            {submitState === "ok" && (
              <span className="text-green-600 text-xs">Gespeichert.</span>
            )}
            {submitState === "err" && (
              <span className="text-red-600 text-xs">Speichern fehlgeschlagen.</span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

