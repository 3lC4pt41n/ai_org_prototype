import React, { useEffect, useState } from "react";
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
  created_at: string;
}

interface Props {
  title: string;
  artifact: Artifact;
  statusIcon: React.ReactNode;
  showFeedback: boolean;
}

function extractOpenQuestions(md: string): string[] {
  const lines = md.split(/\r?\n/);
  const result: string[] = [];
  let inSection = false;
  for (const line of lines) {
    if (/^(?:\*\*|#+)\s*Open Questions/i.test(line)) {
      inSection = true;
      continue;
    }
    if (inSection) {
      if (/^#+\s+/.test(line)) break;
      const m = line.match(/^\s*(?:[-*]|\d+[.)])\s+(.*)/);
      if (m) result.push(m[1].trim());
    }
  }
  return result;
}

export default function ArtifactSection({
  title,
  artifact,
  statusIcon,
  showFeedback,
}: Props) {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<string[]>([]);
  const [feedbacks, setFeedbacks] = useState<FeedbackEntry[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [submitState, setSubmitState] = useState<"idle" | "success" | "error">(
    "idle"
  );

  useEffect(() => {
    let isMounted = true;
    async function load() {
      if (!artifact?.id) return;
      setLoading(true);
      try {
        if (artifact.url) {
          const res = await fetch(artifact.url, {
            headers: {
              Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
            },
          });
          const text = await res.text();
          if (!isMounted) return;
          setContent(text);
          const qs = extractOpenQuestions(text);
          setQuestions(qs);
          setAnswers(new Array(qs.length).fill(""));
        }
        const fbRes = await api.get(`/artifacts/${artifact.id}/feedback`);
        if (isMounted) {
          const list = Array.isArray(fbRes.data)
            ? fbRes.data.sort((a: any, b: any) => a.version - b.version)
            : [];
          setFeedbacks(list);
          setCurrentIdx(list.length > 0 ? list.length - 1 : 0);
        }
      } catch {
        if (isMounted) {
          setContent("");
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    load();
    return () => {
      isMounted = false;
    };
  }, [artifact]);

  const handleAnswerChange = (idx: number, value: string) => {
    const arr = [...answers];
    arr[idx] = value;
    setAnswers(arr);
  };

  const handleSubmit = async () => {
    const payload = {
      answers: questions.map((q, i) => ({ question: q, answer: answers[i] || "" })),
    };
    try {
      await api.post(`/artifacts/${artifact.id}/feedback`, payload);
      setSubmitState("success");
      const fbRes = await api.get(`/artifacts/${artifact.id}/feedback`);
      const list = Array.isArray(fbRes.data)
        ? fbRes.data.sort((a: any, b: any) => a.version - b.version)
        : [];
      setFeedbacks(list);
      setCurrentIdx(list.length > 0 ? list.length - 1 : 0);
    } catch {
      setSubmitState("error");
    }
  };

  const renderFeedback = (fb: FeedbackEntry) => {
    try {
      const parsed = JSON.parse(fb.content);
      if (Array.isArray(parsed)) {
        return (
          <ul className="list-disc ml-5">
            {parsed.map((qa: any, i: number) => (
              <li key={i} className="mb-1">
                <p>
                  <strong>Q:</strong> {qa.question}
                </p>
                <p>
                  <strong>A:</strong> {qa.answer}
                </p>
              </li>
            ))}
          </ul>
        );
      }
    } catch {}
    return <p className="whitespace-pre-wrap">{fb.content}</p>;
  };

  return (
    <section className="mb-6">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <span>{statusIcon}</span>
        {title}
      </h2>
      {loading ? (
        <p className="text-sm text-gray-500">Lade...</p>
      ) : (
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}
      {feedbacks.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <button
              className="px-2 py-1 border rounded"
              onClick={() => setCurrentIdx((i) => i - 1)}
              disabled={currentIdx === 0}
            >
              ◀
            </button>
            <span className="text-sm">
              Feedback {currentIdx + 1} von {feedbacks.length}
            </span>
            <button
              className="px-2 py-1 border rounded"
              onClick={() => setCurrentIdx((i) => i + 1)}
              disabled={currentIdx === feedbacks.length - 1}
            >
              ▶
            </button>
          </div>
          <div className="p-2 border rounded bg-white text-sm">
            {renderFeedback(feedbacks[currentIdx])}
          </div>
        </div>
      )}
      {showFeedback && questions.length > 0 && (
        <div className="mt-4">
          {questions.map((q, idx) => (
            <div key={idx} className="mb-3">
              <p className="font-medium text-sm">{q}</p>
              <textarea
                className="w-full p-2 border rounded text-sm"
                rows={3}
                value={answers[idx] || ""}
                onChange={(e) => handleAnswerChange(idx, e.target.value)}
              />
            </div>
          ))}
          <button
            className="px-3 py-1 bg-blue-600 text-white rounded text-sm"
            onClick={handleSubmit}
          >
            Feedback senden
          </button>
          {submitState === "error" && (
            <p className="text-red-600 text-sm mt-1">
              Fehler beim Speichern des Feedbacks.
            </p>
          )}
          {submitState === "success" && (
            <p className="text-green-600 text-sm mt-1">Feedback gespeichert.</p>
          )}
        </div>
      )}
    </section>
  );
}

