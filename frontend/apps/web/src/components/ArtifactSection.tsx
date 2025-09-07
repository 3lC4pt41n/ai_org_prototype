import { useEffect, useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../lib/api";
import { toast } from "react-hot-toast";
import FileViewer from "./FileViewer";

interface Artifact {
  id: string;
  url?: string;
}

interface FeedbackEntry {
  id: string;
  version: number;
  content: string;
  created_at?: string;
  author?: string;
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
  const [contentType, setContentType] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const filename = artifact?.url ? artifact.url.split("/").pop() || null : null;

  const [history, setHistory] = useState<FeedbackEntry[]>([]);
  const [draft, setDraft] = useState<string>("");
  const [submitState, setSubmitState] = useState<"idle" | "ok" | "err">("idle");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const historyEndRef = useRef<HTMLDivElement | null>(null);

  async function loadArtifact(signal?: AbortSignal) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(artifact.url ?? `/api/artifact/${artifact.id}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token") || ""}` },
        signal,
      });
      if (!res.ok) throw new Error(`artifact ${res.status}`);
      const ct = res.headers.get("content-type");
      setContentType(ct);
      if (
        ct?.startsWith("text/") ||
        ct?.includes("json") ||
        ct?.includes("xml") ||
        ct?.includes("yaml") ||
        ct?.includes("markdown") ||
        ct?.includes("javascript")
      ) {
        const text = await res.text();
        setContent(text);
        if (blobUrl) {
          URL.revokeObjectURL(blobUrl);
          setBlobUrl(null);
        }
      } else {
        const b = await res.blob();
        const url = URL.createObjectURL(b);
        if (blobUrl) URL.revokeObjectURL(blobUrl);
        setBlobUrl(url);
        setContent("");
      }
    } catch {
      setContent("");
      setError("Artefakt konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    loadArtifact(controller.signal);
    return () => {
      controller.abort();
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
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

  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history.length]);

  async function sendFeedback() {
    if (!draft.trim()) {
      toast.error("Bitte Feedback eingeben.");
      return;
    }
    setSubmitting(true);
    setSubmitState("idle");
    const tId = toast.loading("Feedback wird gespeichert …");
    try {
      await api.post(`/artifacts/${artifact.id}/feedback`, { content: draft.trim() });
      setDraft("");
      setSubmitState("ok");
      toast.success("Feedback gespeichert – Product Owner aktualisiert das PRD.", { id: tId });
      // neu laden
      const r = await api.get(`/artifacts/${artifact.id}/feedback`);
      const list: FeedbackEntry[] = Array.isArray(r.data) ? r.data : [];
      setHistory(list);
      await loadArtifact();
    } catch {
      setSubmitState("err");
      toast.error("Speichern fehlgeschlagen.", { id: tId });
    } finally {
      setSubmitting(false);
    }
  }

  async function approveFeedback() {
    setSubmitState("idle");
    setSubmitting(true);
    const tId = toast.loading("Freigabe wird verarbeitet …");
    try {
      await api.post(`/artifacts/${artifact.id}/feedback`, {
        content: draft.trim() || "",
        approved: true,
      });
      setDraft("");
      setSubmitState("ok");
      toast.success("Freigegeben – Architektur wird erstellt & Plan erzeugt.", { id: tId });
      const r = await api.get(`/artifacts/${artifact.id}/feedback`);
      const list: FeedbackEntry[] = Array.isArray(r.data) ? r.data : [];
      setHistory(list);
      await loadArtifact();
    } catch {
      setSubmitState("err");
      toast.error("Freigabe fehlgeschlagen.", { id: tId });
    } finally {
      setSubmitting(false);
    }
  }

  function renderFeedback(fb: FeedbackEntry) {
    try {
      const parsed = JSON.parse(fb.content);
      if (Array.isArray(parsed)) {
        return (
          <ul className="list-disc ml-4 text-sm">
            {parsed.map((qa: any, i: number) => (
              <li key={i} className="mb-1">
                <p>
                  <b>Q:</b> {qa.question}
                </p>
                <p>
                  <b>A:</b> {qa.answer}
                </p>
              </li>
            ))}
          </ul>
        );
      }
    } catch {
      /* ignore – treat as markdown */
    }
    return <ReactMarkdown className="prose prose-sm">{fb.content}</ReactMarkdown>;
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
          <FileViewer
            text={content}
            blobUrl={blobUrl}
            contentType={contentType}
            filename={filename}
            height={520}
          />
        )}
      </div>

      {/* Feedback-Historie */}
      {history.length > 0 && (
        <div className="mb-3 p-3 border rounded bg-white space-y-3 max-h-60 overflow-y-auto">
          {history.map((fb) => (
            <div key={fb.id} className="border-b pb-2 last:border-b-0">
              <div className="text-xs text-gray-600 mb-1">
                {fb.author || "User"}
                {fb.created_at && (
                  <span className="ml-1">
                    {new Date(fb.created_at).toLocaleString()}
                  </span>
                )}
              </div>
              {renderFeedback(fb)}
            </div>
          ))}
          <div ref={historyEndRef} />
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
              disabled={!draft.trim() || submitting}
            >
              Feedback senden
            </button>
            <button
              className="px-3 py-1 bg-green-600 text-white rounded text-sm"
              onClick={approveFeedback}
              disabled={submitting}
            >
              Freigeben
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
