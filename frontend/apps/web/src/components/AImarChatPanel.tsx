import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'react-hot-toast';
import { getJson, postJson } from '../lib/api';

interface Message {
  id: string;
  role: string;
  content: string;
  author?: string;
  created_at?: string;
}

interface ChatPanelProps {
  purposeId: string;
  paused?: boolean;
}

export default function AImarChatPanel({ purposeId, paused = false }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const historyEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!purposeId) return;
    let alive = true;
    getJson<Message[]>(`/chat/history?purpose_id=${purposeId}`)
      .then((data) => {
        if (!alive) return;
        setMessages(Array.isArray(data) ? data : []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [purposeId]);

  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: Message = {
      id: Math.random().toString(36).slice(2, 10),
      role: 'user',
      content: text,
      author: 'You',
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setDraft('');
    setLoading(true);
    try {
      const reply = await postJson<Message>('/chat', { purpose_id: purposeId, message: text });
      setMessages((prev) => [...prev, reply]);
    } catch (err) {
      toast.error('Nachricht konnte nicht gesendet werden.');
    } finally {
      setLoading(false);
    }
  };

  const suggestions = paused ? ['Klingt unklar', 'Fehlt Akzeptanzkriterium'] : [];

  return (
    <div className="flex flex-col h-full border-t pt-2">
      <h3 className="text-sm font-medium mb-2">AImar Chat</h3>
      <div className="flex-1 overflow-y-auto mb-2">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`my-1 max-w-[80%] p-2 rounded text-sm ${
              m.role === 'user'
                ? 'bg-blue-100 text-blue-900 ml-auto'
                : 'bg-gray-100 text-gray-800 mr-auto'
            }`}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
          </div>
        ))}
        <div ref={historyEndRef} />
      </div>
      {suggestions.length > 0 && (
        <div className="mb-2 space-x-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              className="text-xs px-2 py-1 bg-gray-200 hover:bg-gray-300 rounded"
              onClick={() => sendMessage(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <input
          type="text"
          className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm"
          placeholder="Schreibe eine Nachricht..."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              sendMessage(draft);
            }
          }}
        />
        <button
          className="bg-blue-600 text-white text-sm px-3 py-1 rounded disabled:opacity-50"
          onClick={() => sendMessage(draft)}
          disabled={loading || !draft.trim()}
        >
          Senden
        </button>
      </div>
    </div>
  );
}

