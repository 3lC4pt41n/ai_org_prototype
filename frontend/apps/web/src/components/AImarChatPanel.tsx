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
  const [useWs, setUseWs] = useState(false);
  const historyEndRef = useRef<HTMLDivElement | null>(null);
  const loadingRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);

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
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [purposeId]);

  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  useEffect(() => {
    if (!purposeId) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const token = localStorage.getItem('access_token') || localStorage.getItem('token');
    const wsUrl = `${protocol}//${host}/ws/chat/${purposeId}${token ? `?token=${token}` : ''}`;
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;
    socket.onopen = () => {
      setUseWs(true);
    };
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.error) {
        toast.error(data.error);
        setLoading(false);
        loadingRef.current = false;
      } else {
        setMessages((prev) => [...prev, data]);
        setLoading(false);
        loadingRef.current = false;
      }
    };
    socket.onclose = () => {
      if (loadingRef.current) {
        toast.error('Verbindung zum Chat unterbrochen.');
        setLoading(false);
      }
      setUseWs(false);
      wsRef.current = null;
      loadingRef.current = false;
    };
    return () => {
      socket.close();
    };
  }, [purposeId]);

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
    loadingRef.current = true;
    if (useWs && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ message: text }));
      } catch (err) {
        try {
          const reply = await postJson<Message>('/chat', {
            purpose_id: purposeId,
            message: text,
          });
          setMessages((prev) => [...prev, reply]);
        } catch (err2) {
          toast.error('Nachricht konnte nicht gesendet werden.');
        } finally {
          setLoading(false);
          loadingRef.current = false;
          setUseWs(false);
        }
      }
    } else {
      try {
        const reply = await postJson<Message>('/chat', {
          purpose_id: purposeId,
          message: text,
        });
        setMessages((prev) => [...prev, reply]);
      } catch (err) {
        toast.error('Nachricht konnte nicht gesendet werden.');
      } finally {
        setLoading(false);
        loadingRef.current = false;
      }
    }
  };

  const suggestions = paused
    ? ['Klingt unklar', 'Fehlt Akzeptanzkriterium', 'Kein Businessziel']
    : [];

  return (
    <div className="flex flex-col h-full border-t pt-2">
      <h3 className="text-sm font-medium mb-2">AImar Chat</h3>
      <div className="text-xs text-gray-600 mb-2 flex items-center gap-2">
        <span role="img" aria-label="Robot">
          🤖
        </span>
        <span>KI-Produkt Owner Assistent (professionell, kritisch, fordernd)</span>
      </div>
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
