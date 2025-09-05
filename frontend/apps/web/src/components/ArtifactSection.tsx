import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../lib/api";

interface Artifact {
  id: string;
  url?: string;
}

interface ArtifactSectionProps {
  title: string;
  artifact: Artifact;
  statusIcon: React.ReactNode;
  showFeedback: boolean;
}

interface FeedbackEntry {
  id: string;
  content: string;
  version: number;
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
}: ArtifactSectionProps) {
  const [content, setContent] = useState(" ");
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<string[]>([]);
  const [feedbacks, setFeedbacks] = useState<FeedbackEntry[]>([]);
  const [idx, setIdx] = useState(0);
  const [submitState, setSubmitState] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(artifact.url ?? `/api/artifact/${artifact.id}`, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
          },
        });
        const text = await res.text();
        setContent(text);
        const qs = extractOpenQuestions(text);
        setQuestions(qs);
        setAnswers(new Array(qs.length).fill(""));
      } catch {
        setContent("" );
      }

      try {
        const r = await api.get(`/artifacts/${artifact.id}/feedback`);
        const list: FeedbackEntry[] = Array.isArray(r.data) ? r.data : [];
        setFeedbacks(list);
        setIdx(list.length > 0 ? list.length - 1 : 0);
      } catch {
        setFeedbacks([]);
      }
    }
    load();
  }, [artifact.id, artifact.url]);

  const handleAnswerChange = (i: number, v: string) => {
    const arr = [...answers];
    arr[i] = v;
    setAnswers(arr);
  };

  const handleSubmit = async () => {
    const payload = {
      answers: questions.map((q, i) => ({ question: q, answer: answers[i] || "" })),
    };
    try {
      await api.post(`/artifacts/${artifact.id}/feedback`, payload);
      const r = await api.get(`/artifacts/${artifact.id}/feedback`);
      const list: FeedbackEntry[] = Array.isArray(r.data) ? r.data : [];
      setFeedbacks(list);
      setIdx(list.length > 0 ? list.length - 1 : 0);
      setSubmitState("success");
    } catch {
      setSubmitState("error");
    }
  };

  const currentFeedback = feedbacks[idx];
  let parsedQA: { question: string; answer: string }[] | null = null;
  if (currentFeedback) {
    try {
      const p = JSON.parse(currentFeedback.content);
      if (Array.isArray(p)) parsedQA = p;
    } catch {
      parsedQA = null;
    }
  }

  return (
    <section className="p-4 border-b">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <span>{statusIcon}</span>
        {title}
      </h2>
      {content && (
        <div className="prose max-w-none mb-4">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}
      {showFeedback && questions.length > 0 && (
        <div className="mb-4">
          {questions.map((q, i) => (
            <div key={i} className="mb-2">
              <p className="font-medium text-sm">{q}</p>
              <textarea
                rows={3}
                className="w-full p-2 border rounded text-sm"
                value={answers[i] || ""}
                onChange={(e) => handleAnswerChange(i, e.target.value)}
              />
            </div>
          ))}
          <button
            className="mt-2 px-3 py-1 bg-blue-600 text-white rounded text-sm"
            onClick={handleSubmit}
          >
            Feedback senden
          </button>
          {submitState === "success" && (
            <p className="text-green-600 text-sm mt-1">Feedback gespeichert.</p>
          )}
          {submitState === "error" && (
            <p className="text-red-600 text-sm mt-1">Fehler beim Speichern.</p>
          )}
        </div>
      )}
      {feedbacks.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2 text-sm">
            <button
              className="px-2 py-1 border rounded disabled:opacity-50"
              onClick={() => setIdx((i) => Math.max(0, i - 1))}
              disabled={idx === 0}
            >
              ◀️
            </button>
            <span>
              Feedback {idx + 1} / {feedbacks.length}
            </span>
            <button
              className="px-2 py-1 border rounded disabled:opacity-50"
              onClick={() => setIdx((i) => Math.min(feedbacks.length - 1, i + 1))}
              disabled={idx === feedbacks.length - 1}
            >
              ▶️
            </button>
          </div>
          <div className="p-2 border rounded bg-white text-sm whitespace-pre-wrap">
            {parsedQA ? (
              parsedQA.map((qa, i) => (
                <div key={i} className="mb-2">
                  <p className="font-medium">Q: {qa.question}</p>
                  <p>A: {qa.answer}</p>
                </div>
              ))
            ) : (
              <ReactMarkdown>{currentFeedback?.content || ""}</ReactMarkdown>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

