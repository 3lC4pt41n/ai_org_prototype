import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../lib/api";

interface Task {
  id: string;
  phase: string;
  description: string;
  artifactUrl?: string;
  artifactId?: string;
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

const FeedbackSection: React.FC<{ tasks: Task[] }> = ({ tasks }) => {
  const [contents, setContents] = useState<Record<string, string>>({});
  const [questions, setQuestions] = useState<Record<string, string[]>>({});
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [status, setStatus] = useState<Record<string, string>>({});

  useEffect(() => {
    tasks.forEach((task) => {
      if (!task.artifactUrl) return;
      fetch(task.artifactUrl, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
        },
      })
        .then((r) => r.text())
        .then((text) => {
          setContents((p) => ({ ...p, [task.id]: text }));
          const qs = extractOpenQuestions(text);
          setQuestions((p) => ({ ...p, [task.id]: qs }));
          setAnswers((p) => ({ ...p, [task.id]: new Array(qs.length).fill("") }));
        })
        .catch(() => {
          setContents((p) => ({ ...p, [task.id]: "" }));
        });
    });
  }, [tasks]);

  const handleAnswerChange = (taskId: string, idx: number, value: string) => {
    setAnswers((prev) => {
      const arr = [...(prev[taskId] || [])];
      arr[idx] = value;
      return { ...prev, [taskId]: arr };
    });
  };

  const handleSubmit = async (task: Task) => {
    const qs = questions[task.id] || [];
    const ans = answers[task.id] || [];
    const payload = {
      answers: qs.map((q, i) => ({ question: q, answer: ans[i] || "" })),
    };
    try {
      await api.post(`/artifacts/${task.artifactId}/feedback`, payload);
      setStatus((p) => ({ ...p, [task.id]: "success" }));
    } catch (e) {
      setStatus((p) => ({ ...p, [task.id]: "error" }));
    }
  };

  return (
    <div className="feedback-section">
      <h3 className="mb-2 font-semibold">Feedback</h3>
      {tasks.map((task) => (
        <div key={task.id} className="mb-6">
          <p className="text-sm">
            <strong>{task.phase}:</strong> {task.description}
          </p>
          {contents[task.id] && (
            <div className="my-2 p-2 border rounded bg-white max-h-64 overflow-auto">
              <div className="prose prose-slate">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {contents[task.id]}
                </ReactMarkdown>
              </div>
            </div>
          )}
          {(questions[task.id] || []).map((q, idx) => (
            <div key={idx} className="mb-2">
              <p className="font-medium text-sm">{q}</p>
              <textarea
                rows={3}
                className="w-full p-2 border rounded text-sm"
                placeholder="Your answer..."
                value={(answers[task.id] || [])[idx] || ""}
                onChange={(e) => handleAnswerChange(task.id, idx, e.target.value)}
              />
            </div>
          ))}
          {questions[task.id] && questions[task.id].length > 0 && (
            <button
              className="mt-2 px-3 py-1 bg-blue-600 text-white rounded text-sm"
              onClick={() => handleSubmit(task)}
            >
              Feedback senden
            </button>
          )}
          {status[task.id] === "error" && (
            <p className="text-red-600 text-sm mt-1">
              Failed to submit feedback. Please try again.
            </p>
          )}
          {status[task.id] === "success" && (
            <p className="text-green-600 text-sm mt-1">Feedback gespeichert.</p>
          )}
        </div>
      ))}
    </div>
  );
};

export default FeedbackSection;
