import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'react-hot-toast';
import { getJson, postJson, API_BASE } from '../lib/api';
import usePipelineStore from '../store/pipelineStore';
import {
  getFeedbackForArtifact,
  postFeedbackForArtifact,
  type ArtifactFeedbackMessage,
} from '../api/api.artifacts';
import { formatDateTime } from '../lib/datetime';
import { usePipelineCopy } from '../i18n/pipeline';

export interface ArtifactChatContext {
  artifactId: string;
  artifactTitle: string;
  phaseLabel?: string;
  phaseKey?: string;
  artifactReleased?: boolean;
}

enum ChatRole {
  USER = 'user',
  ASSISTANT = 'assistant',
  AGENT = 'agent',
}

interface Message {
  id: string;
  role: ChatRole;
  content: string;
  author?: string;
  created_at?: string;
  artifact_ids?: string[];
}

export interface ChatPanelProps {
  purposeId: string | null;
  paused?: boolean;
  filterValue?: string;
  onFilterValueChange?: (value: string) => void;
  artifactContext?: ArtifactChatContext | null;
  onFeedbackSubmitted?: () => void;
  onArtifactApproved?: () => void;
}

function ArtifactChatPanel({
  context,
  paused = false,
  onFeedbackSubmitted,
  onArtifactApproved,
  purposeId,
}: {
  context: ArtifactChatContext;
  paused?: boolean;
  onFeedbackSubmitted?: () => void;
  onArtifactApproved?: () => void;
  purposeId: string;
}) {
  const { artifactId, artifactTitle, phaseLabel, artifactReleased } = context;
  const { chat } = usePipelineCopy();
  const [messages, setMessages] = useState<ArtifactFeedbackMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const lastMessageCountRef = useRef(0);
  const INITIAL_VISIBLE = 30;
  const [visibleCount, setVisibleCount] = useState<number>(INITIAL_VISIBLE);

  useEffect(() => {
    let canceled = false;
    setIsLoading(true);
    shouldAutoScrollRef.current = true;
    lastMessageCountRef.current = 0;
    setVisibleCount(INITIAL_VISIBLE);
    async function load() {
      try {
        const list = await getFeedbackForArtifact(artifactId);
        if (!canceled) {
          setMessages(list);
          setVisibleCount((prev) => {
            if (!list.length) return INITIAL_VISIBLE;
            const baseline = Math.max(prev, INITIAL_VISIBLE);
            return Math.min(list.length, baseline);
          });
        }
      } catch (error) {
        console.error('Artifact feedback could not be loaded', error);
        if (!canceled) {
          toast.error(chat.loadError);
          setMessages([]);
        }
      } finally {
        if (!canceled) {
          setIsLoading(false);
        }
      }
    }
    void load();
    return () => {
      canceled = true;
    };
  }, [artifactId]);

  useEffect(() => {
    if (!messages.length) {
      lastMessageCountRef.current = 0;
      return;
    }
    const previousCount = lastMessageCountRef.current;
    const added = messages.length - previousCount;
    if (added > 0 && shouldAutoScrollRef.current) {
      endRef.current?.scrollIntoView({ behavior: previousCount === 0 ? 'auto' : 'smooth' });
    }
    lastMessageCountRef.current = messages.length;
    shouldAutoScrollRef.current = false;
  }, [messages]);

  async function refreshMessages() {
    try {
      const list = await getFeedbackForArtifact(artifactId);
      setMessages(list);
      setVisibleCount((prev) => {
        if (!list.length) return INITIAL_VISIBLE;
        const baseline = Math.max(prev, INITIAL_VISIBLE);
        return Math.min(list.length, baseline);
      });
      shouldAutoScrollRef.current = true;
    } catch (error) {
      console.error('Unable to refresh artifact feedback', error);
      toast.error(chat.refreshError);
    }
  }

  async function handleSend(intent: 'feedback' | 'question' | 'note' | 'approval' = 'feedback') {
    const text = input.trim();
    if (!text && intent !== 'approval') return;
    if (isSubmitting) return;

    setIsSubmitting(true);
    try {
      if (intent === 'approval') {
        await postFeedbackForArtifact(artifactId, text || 'Approved', 'approval');
      } else {
        await postFeedbackForArtifact(artifactId, text, intent);
      }

      if (intent === 'approval') {
        await postJson('/chat/messages', {
          purpose_id: purposeId,
          artifact_ids: [artifactId],
          intent: 'approval',
          message: text || 'Approved',
        });
      } else {
        const messageIntent = /\?\s*$/.test(text) ? 'question' : intent;
        await postJson('/chat/messages', {
          purpose_id: purposeId,
          artifact_ids: [artifactId],
          intent: messageIntent,
          message: text,
        });
      }
      setInput('');
      shouldAutoScrollRef.current = true;
      await refreshMessages();
      onFeedbackSubmitted?.();
      if (intent === 'approval') {
        toast.success(chat.approveSuccess);
        onArtifactApproved?.();
      }
    } catch (error) {
      console.error('Unable to send feedback', error);
      toast.error(chat.submitError);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      void handleSend();
    }
  }

  const hasMessages = messages.length > 0;
  const releaseDisabled = artifactReleased;
  const hasMore = messages.length > visibleCount;
  const visibleMessages = hasMore ? messages.slice(messages.length - visibleCount) : messages;

  function handleLoadMore() {
    setVisibleCount((prev) => Math.min(messages.length, prev + INITIAL_VISIBLE));
    shouldAutoScrollRef.current = false;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
        <div className="font-medium text-slate-700 dark:text-slate-200">{phaseLabel ?? 'Phase'}</div>
        <div className="text-[11px] uppercase tracking-wide text-slate-500">
          Artefakt: {artifactTitle}
        </div>
      </div>

      <div className="flex-1 rounded-lg border border-slate-200 bg-white p-4 shadow-inner dark:border-slate-700 dark:bg-slate-900/60">
        {isLoading ? (
          <p className="text-sm text-slate-500">{chat.loading}</p>
        ) : hasMessages ? (
          <div className="space-y-3 overflow-y-auto pr-2 text-sm max-h-[320px]">
            {hasMore && (
              <div className="flex justify-center">
                <button
                  type="button"
                  className="rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-700 dark:border-slate-600 dark:text-slate-300 dark:hover:border-slate-500 dark:hover:text-slate-100"
                  onClick={handleLoadMore}
                  disabled={isLoading}
                >
                  {chat.loadMore}
                </button>
              </div>
            )}
            {visibleMessages.map((msg) => {
              const timestamp = msg.created_at ?? msg.createdAt ?? null;
              const body = msg.content ?? msg.text ?? msg.markdown ?? '';
              const intent = msg.intent ?? 'feedback';
              const isUser = msg.role === 'user';
              const bubbleClasses = isUser
                ? 'ml-auto max-w-[85%] rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white'
                : 'mr-auto max-w-[85%] rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-800 dark:bg-slate-800/80 dark:text-slate-100';
              return (
                <div key={msg.id ?? `${timestamp}-${body.slice(0, 12)}`} className="flex flex-col">
                  <div className={bubbleClasses}>
                    <div className="text-[11px] font-medium uppercase tracking-wide text-white/80">
                      {intent === 'approval'
                        ? chat.intent.approval
                        : intent === 'question'
                          ? chat.intent.question
                          : chat.intent.feedback}
                    </div>
                    <div className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
                      {body || <span className="italic text-slate-200">(kein Inhalt)</span>}
                    </div>
                  </div>
                  {timestamp && (
                    <span className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                      {formatDateTime(timestamp) ?? ''}
                    </span>
                  )}
                </div>
              );
            })}
            <div ref={endRef} />
          </div>
        ) : (
          <p className="text-sm text-slate-500">{chat.noMessages}</p>
        )}
      </div>

      <div className="space-y-2">
        {paused && (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">{chat.pausedNotice}</p>
        )}
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-200" htmlFor={`feedback-${artifactId}`}>
          {chat.textareaLabel}
        </label>
        <textarea
          id={`feedback-${artifactId}`}
          rows={3}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
          placeholder={chat.textareaPlaceholder}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isSubmitting}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void handleSend()}
            disabled={isSubmitting || !input.trim()}
          >
            {chat.send}
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void handleSend('approval')}
            disabled={isSubmitting || releaseDisabled}
          >
            {chat.approve}
          </button>
        </div>
      </div>
    </div>
  );
}

function LegacyChatPanel({
  purposeId,
  paused = false,
  filterValue: controlledFilterValue,
  onFilterValueChange,
}: ChatPanelProps) {
  const artifacts = usePipelineStore((s) => s.artifacts);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [useWs, setUseWs] = useState(false);
  const historyEndRef = useRef<HTMLDivElement | null>(null);
  const loadingRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);
  const [scope, setScope] = useState<'global' | 'artifact' | 'auto'>('global');
  const [selectedArtifacts, setSelectedArtifacts] = useState<string[]>([]);
  const [suggestionsMap, setSuggestionsMap] = useState<Record<string, string[]>>({});
  const [localFilterValue, setLocalFilterValue] = useState<string>('all');
  const activeFilterValue = controlledFilterValue ?? localFilterValue;

  useEffect(() => {
    if (controlledFilterValue !== undefined) {
      setLocalFilterValue(controlledFilterValue);
    }
  }, [controlledFilterValue]);

  const handleFilterChange = (value: string) => {
    if (controlledFilterValue === undefined) {
      setLocalFilterValue(value);
    }
    onFilterValueChange?.(value);
  };

  const formatArtifactLabel = (artifact: any) => {
    if (!artifact) return '';
    const fileName = artifact.repo_path?.split('/').pop() || '';
    if (fileName.toLowerCase().includes('product_requirements')) return 'Produktanforderung';
    if (fileName.toLowerCase().includes('architecture_domain_review'))
      return 'Architektur & Domain Review';
    if (fileName.toLowerCase().includes('architecture_blueprint')) return 'Architektur';
    const name = fileName.replace(/_/g, ' ');
    return name.charAt(0).toUpperCase() + name.slice(1);
  };

  const handleAddTag = async (messageId: string, artifactId: string) => {
    const msg = messages.find((m) => m.id === messageId);
    const currentIds: string[] = (msg && (msg as any).artifact_ids) || [];
    const newIds = currentIds.includes(artifactId) ? currentIds : [...currentIds, artifactId];
    const token = localStorage.getItem('token');
    try {
      await fetch(`${API_BASE}/chat/messages/${messageId}/tags`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ artifact_ids: newIds }),
      });
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, artifact_ids: newIds } : m)),
      );
      setSuggestionsMap((prev) => {
        const updated = { ...prev };
        const remaining = updated[messageId]?.filter((id: string) => id !== artifactId);
        if (!remaining || remaining.length === 0) {
          delete updated[messageId];
        } else {
          updated[messageId] = remaining;
        }
        return updated;
      });
    } catch {
      toast.error('Tag konnte nicht hinzugefügt werden.');
    }
  };

  useEffect(() => {
    if (!purposeId) return;
    let alive = true;
    getJson<Message[]>(`/chat/messages?purpose_id=${purposeId}`)
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
    if (activeFilterValue === 'all' || activeFilterValue === 'global') {
      setScope('global');
      if (activeFilterValue !== 'global') {
        setSelectedArtifacts([]);
      }
    } else if (activeFilterValue) {
      setScope('artifact');
      setSelectedArtifacts([activeFilterValue]);
    }
  }, [activeFilterValue]);

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
        if (data.suggested_artifact_ids) {
          const userMsgId = data.user_message_id;
          setMessages((prev) =>
            prev.map((m, i) => (i === prev.length - 1 ? { ...m, id: userMsgId } : m)),
          );
          setSuggestionsMap((prev) => ({ ...prev, [userMsgId]: data.suggested_artifact_ids }));
        }
        const assistantMsg: Message = {
          id: data.id,
          role: data.role,
          content: data.content,
          author: 'AImar',
          created_at: data.created_at,
        };
        setMessages((prev) => [...prev, assistantMsg]);
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
    if (!text.trim() || loading || !purposeId) return;
    const userMsg: Message = {
      id: Math.random().toString(36).slice(2, 10),
      role: ChatRole.USER,
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
        const msgPayload: any = { message: text };
        if (scope === 'artifact') {
          msgPayload.artifact_ids = selectedArtifacts;
          msgPayload.scope = selectedArtifacts.length > 1 ? 'mixed' : 'artifact';
        } else if (scope === 'auto') {
          msgPayload.scope = 'auto';
        }
        wsRef.current.send(JSON.stringify(msgPayload));
      } catch (err) {
        try {
          const payload: any = { purpose_id: purposeId, message: text };
          if (scope === 'artifact') {
            payload.artifact_ids = selectedArtifacts;
            payload.scope = selectedArtifacts.length > 1 ? 'mixed' : 'artifact';
          } else if (scope === 'auto') {
            payload.scope = 'auto';
          }
          const replyData = await postJson<any>('/chat/messages', payload);
          if (replyData.suggested_artifact_ids) {
            const userMsgId = replyData.user_message_id;
            setMessages((prev) =>
              prev.map((m, i) => (i === prev.length - 1 ? { ...m, id: userMsgId } : m)),
            );
            setSuggestionsMap((prev) => ({ ...prev, [userMsgId]: replyData.suggested_artifact_ids }));
          }
          const assistantMsg: Message = {
            id: replyData.id,
            role: replyData.role,
            content: replyData.content,
            author: 'AImar',
            created_at: replyData.created_at,
          };
          setMessages((prev) => [...prev, assistantMsg]);
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
        const payload: any = { purpose_id: purposeId, message: text };
        if (scope === 'artifact') {
          payload.artifact_ids = selectedArtifacts;
          payload.scope = selectedArtifacts.length > 1 ? 'mixed' : 'artifact';
        } else if (scope === 'auto') {
          payload.scope = 'auto';
        }
        const replyData = await postJson<any>('/chat/messages', payload);
        if (replyData.suggested_artifact_ids) {
          const userMsgId = replyData.user_message_id;
          setMessages((prev) =>
            prev.map((m, i) => (i === prev.length - 1 ? { ...m, id: userMsgId } : m)),
          );
          setSuggestionsMap((prev) => ({ ...prev, [userMsgId]: replyData.suggested_artifact_ids }));
        }
        const assistantMsg: Message = {
          id: replyData.id,
          role: replyData.role,
          content: replyData.content,
          author: 'AImar',
          created_at: replyData.created_at,
        };
        setMessages((prev) => [...prev, assistantMsg]);
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
      <div className="mb-2">
        <select
          value={activeFilterValue}
          onChange={(e) => handleFilterChange(e.target.value)}
          className="w-full max-w-[220px] text-xs border border-slate-300 rounded px-1 py-0.5"
        >
          <option value="all">Alle Nachrichten</option>
          <option value="global">Nur globale</option>
          {artifacts
            .filter((a: any) => a.media_type?.startsWith('text/'))
            .map((a: any) => (
              <option key={a.id} value={a.id}>
                Nur {formatArtifactLabel(a)}
              </option>
            ))}
        </select>
      </div>
      <div className="flex-1 overflow-y-auto mb-2">
        {messages
          .filter((m) => {
            if (activeFilterValue === 'global') {
              return !(m as any).artifact_ids || (m as any).artifact_ids.length === 0;
            }
            if (activeFilterValue && activeFilterValue !== 'all' && activeFilterValue !== 'global') {
              return (m as any).artifact_ids && (m as any).artifact_ids.includes(activeFilterValue);
            }
            return true;
          })
          .map((m) => (
            <div
              key={m.id}
              className={`my-1 max-w-[80%] p-2 rounded text-sm ${
                m.role === ChatRole.USER
                  ? 'bg-blue-100 text-blue-900 ml-auto'
                  : m.role === ChatRole.AGENT
                  ? 'bg-gray-100 text-gray-800 mr-auto ml-4 border-l-4 border-blue-400'
                  : 'bg-gray-100 text-gray-800 mr-auto'
              }`}
            >
              {m.role === ChatRole.AGENT ? (
                (() => {
                  try {
                    const data = JSON.parse(m.content);
                    if (data.betroffene_artefakte) {
                      return (
                        <>
                          <div className="mb-1">
                            <span role="img" aria-label="Hinweis" className="mr-1">
                              ℹ️
                            </span>
                            <b>Betroffene Artefakte:</b>{' '}
                            {data.betroffene_artefakte.length > 0
                              ? data.betroffene_artefakte.join(', ')
                              : 'Keine'}
                          </div>
                          <div className="mb-1">
                            <b>Auswirkungsgrad:</b> {data.impact_level}
                          </div>
                          <div className="mb-1">
                            <b>Änderungstyp:</b> {data.change_type}
                          </div>
                          {data.followup_suggestion && (
                            <div>
                              <b>Folgeaktion:</b> {data.followup_suggestion}
                            </div>
                          )}
                        </>
                      );
                    }
                  } catch {}
                  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>;
                })()
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
              )}
              {(m as any).artifact_ids && (m as any).artifact_ids.length > 0 && (
                <div className="mt-1">
                  {(m as any).artifact_ids.map((aid: string) => {
                    const art = artifacts.find((x: any) => x.id === aid);
                    const label = formatArtifactLabel(art);
                    return (
                      <span
                        key={aid}
                        className="inline-block text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded mr-1"
                        title={art?.repo_path}
                      >
                        {label}
                      </span>
                    );
                  })}
                </div>
              )}
              {suggestionsMap[m.id] && suggestionsMap[m.id].length > 0 && (
                <div className="mt-1 space-x-2">
                  {suggestionsMap[m.id].map((aid: string) => {
                    const art = artifacts.find((x: any) => x.id === aid);
                    const label = formatArtifactLabel(art);
                    return (
                      <button
                        key={aid}
                        type="button"
                        className="text-xs px-2 py-1 bg-gray-200 hover:bg-gray-300 rounded"
                        onClick={() => handleAddTag(m.id, aid)}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              )}
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
      {scope === 'artifact' && (
        <div className="mb-2 text-xs text-gray-700">
          {artifacts
            .filter((a: any) => a.media_type?.startsWith('text/'))
            .map((a: any) => (
              <label key={a.id} className="mr-3">
                <input
                  type="checkbox"
                  checked={selectedArtifacts.includes(a.id)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedArtifacts((prev) => [...prev, a.id]);
                    } else {
                      setSelectedArtifacts((prev) => prev.filter((id) => id !== a.id));
                    }
                  }}
                  className="mr-1"
                />
                {formatArtifactLabel(a)}
              </label>
            ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value as 'global' | 'artifact' | 'auto')}
          className="flex-shrink-0 w-full max-w-[160px] text-xs border border-slate-300 rounded px-2 py-1"
        >
          <option value="global">🌐 Global</option>
          <option value="artifact">🏷️ Artefakt</option>
          <option value="auto">🤖 Auto</option>
        </select>
        <input
          type="text"
          className="flex-1 border border-slate-300 rounded px-3 py-2 text-sm min-h-[44px]"
          placeholder="Schreibe eine Nachricht..."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void sendMessage(draft);
            }
          }}
          disabled={!purposeId}
        />
        <button
          className="bg-blue-600 text-white text-sm px-3 py-1 rounded disabled:opacity-50"
          onClick={() => void sendMessage(draft)}
          disabled={loading || !draft.trim() || !purposeId}
        >
          Senden
        </button>
      </div>
    </div>
  );
}

export default function AImarChatPanel(props: ChatPanelProps) {
  const { purposeId, artifactContext } = props;
  if (artifactContext?.artifactId && purposeId) {
    return (
      <ArtifactChatPanel
        context={artifactContext}
        paused={props.paused}
        onFeedbackSubmitted={props.onFeedbackSubmitted}
        onArtifactApproved={props.onArtifactApproved}
        purposeId={purposeId}
      />
    );
  }
  return <LegacyChatPanel {...props} />;
}
