import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { api } from '../lib/api';

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

interface ArtifactSectionProps {
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
}: ArtifactSectionProps) {
  const [content, setContent] = useState('');
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<string[]>([]);
  const [feedbacks, setFeedbacks] = useState<FeedbackEntry[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [submitStatus, setSubmitStatus] = useState<string>('');

  // load artifact content
  useEffect(() => {
    const url = artifact.url ?? `/api/artifact/${artifact.id}`;
    fetch(url, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
      },
    })
      .then((r) => r.text())
      .then((text) => {
        setContent(text);
        const qs = extractOpenQuestions(text);
        setQuestions(qs);
        setAnswers(new Array(qs.length).fill(''));
      })
      .catch(() => setContent(''));
  }, [artifact.id, artifact.url]);

  // load feedback history
  useEffect(() => {
    api
      .get<FeedbackEntry[]>(`/artifacts/${artifact.id}/feedback`)
      .then((res) => {
        const list = Array.isArray(res.data) ? res.data : [];
        setFeedbacks(list);
        setCurrentIdx(list.length > 0 ? list.length - 1 : 0);
      })
      .catch(() => setFeedbacks([]));
  }, [artifact.id]);

  const handleAnswerChange = (idx: number, value: string) => {
    const arr = [...answers];
    arr[idx] = value;
    setAnswers(arr);
  };

  const handleSubmit = async () => {
    const payload = {
      answers: questions.map((q, i) => ({ question: q, answer: answers[i] || '' })),
    };
    try {
      await api.post(`/artifacts/${artifact.id}/feedback`, payload);
      setSubmitStatus('success');
      const res = await api.get<FeedbackEntry[]>(`/artifacts/${artifact.id}/feedback`);
      const list = Array.isArray(res.data) ? res.data : [];
      setFeedbacks(list);
      setCurrentIdx(list.length > 0 ? list.length - 1 : 0);
    } catch (e) {
      setSubmitStatus('error');
    }
  };

  const renderFeedbackContent = (fb: FeedbackEntry) => {
    try {
      const parsed = JSON.parse(fb.content);
      if (Array.isArray(parsed)) {
        return (
          <ul className="list-disc pl-4">
            {parsed.map((p: any, i: number) => (
              <li key={i} className="mb-2">
                <p>
                  <strong>Q:</strong> {p.question}
                </p>
                <p>
                  <strong>A:</strong> {p.answer}
                </p>
              </li>
            ))}
          </ul>
        );
      }
    } catch {
      /* fall through */
    }
    return <ReactMarkdown>{fb.content}</ReactMarkdown>;
  };

  return (
    <section className="mb-6">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <span>{statusIcon}</span>
        {title}
      </h2>
      <div className="mb-4 p-4 border rounded bg-white">
        {content ? (
          <ReactMarkdown>{content}</ReactMarkdown>
        ) : (
          <p className="text-sm text-gray-500">Loading...</p>
        )}
      </div>
      {showFeedback && questions.length > 0 && (
        <div className="mb-4">
          {questions.map((q, idx) => (
            <div key={idx} className="mb-2">
              <p className="font-medium text-sm">{q}</p>
              <textarea
                rows={3}
                className="w-full p-2 border rounded text-sm"
                value={answers[idx] || ''}
                onChange={(e) => handleAnswerChange(idx, e.target.value)}
              />
            </div>
          ))}
          <button
            className="mt-2 px-3 py-1 bg-blue-600 text-white rounded text-sm"
            onClick={handleSubmit}
          >
            Feedback senden
          </button>
          {submitStatus === 'error' && (
            <p className="text-red-600 text-sm mt-1">
              Failed to submit feedback. Please try again.
            </p>
          )}
          {submitStatus === 'success' && (
            <p className="text-green-600 text-sm mt-1">Feedback gespeichert.</p>
          )}
        </div>
      )}
      {feedbacks.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2 text-sm">
            <button
              className="px-2 py-1 border rounded"
              onClick={() => setCurrentIdx((i) => Math.max(i - 1, 0))}
              disabled={currentIdx === 0}
            >
              ◀
            </button>
            <span>
              Feedback {feedbacks.length === 0 ? 0 : currentIdx + 1} / {feedbacks.length}
            </span>
            <button
              className="px-2 py-1 border rounded"
              onClick={() =>
                setCurrentIdx((i) => Math.min(i + 1, feedbacks.length - 1))
              }
              disabled={currentIdx === feedbacks.length - 1}
            >
              ▶
            </button>
          </div>
          <div className="p-2 border rounded bg-white text-sm">
            {renderFeedbackContent(feedbacks[currentIdx])}
          </div>
        </div>
      )}
    </section>
  );
}

