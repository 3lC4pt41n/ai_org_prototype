import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'react-hot-toast';
import { PlayCircle, PauseCircle, Trash2, ChevronRight } from 'lucide-react';
import usePipelineStore from '../../../store/pipelineStore';
import { API_BASE, getJson, postJson, putJson } from '../../../lib/api';
import { PIPELINE_PHASES } from '../phaseConfig';
import type {
  PhaseViewContext,
  PipelineTemplateSummary,
  ArtifactItem,
  PromptTemplateListResponse,
  PromptTemplateRecord,
  PipelinePhaseDefaults,
} from '../types';

type PhaseConfig = {
  /** echte Phase-ID aus dem Backend (falls vorhanden) */
  phaseId: string | null;
  slug: string;
  name: string;
  model: string;
  tokens: number;
  prompt: string;
  promptTemplateId: string | null;
  promptDefaultPath: string | null;
  promptTenantId: string | null;
  promptIsTenantDefault: boolean;
  isSystemPrompt: boolean;
  agentRole: string | null;
  /** nur speicherbar, wenn eine echte phaseId existiert */
  isUpdatable: boolean;
};

type StoredPhaseDefaults = {
  slug: string;
  model?: string;
  tokens?: number;
  prompt?: string;
};

/**
 * Rohtext-Datei (z. B. .j2) laden.
 * Fallback, wenn ein System-Prompt per default_path referenziert wird,
 * aber noch kein Inhalt in promptTemplates vorhanden ist.
 */
async function fetchTemplateText(path: string): Promise<string> {
  const token = localStorage.getItem('token');
  try {
    const res = await fetch(`${API_BASE}/templates/${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`GET /templates/${path} failed`);
    const text = await res.text();
    return typeof text === 'string' ? text : '';
  } catch (e) {
    console.warn('Failed to fetch template text:', path, e);
    return '';
  }
}

const MODEL_OPTIONS = [
  { value: '', label: 'Standard übernehmen' },
  { value: 'gpt-4', label: 'GPT-4' },
  { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
  { value: 'claude-3-opus', label: 'Claude 3 Opus' },
];

function loadUserPhaseDefaults(): StoredPhaseDefaults[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem('pipelinePhaseDefaults');
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((entry: any) => {
        const slug = typeof entry?.slug === 'string' ? entry.slug : '';
        if (!slug) return null;
        const tokensValue = Number(entry?.tokens);
        return {
          slug,
          model: typeof entry?.model === 'string' ? entry.model : undefined,
          tokens: Number.isFinite(tokensValue) ? tokensValue : undefined,
          prompt: typeof entry?.prompt === 'string' ? entry.prompt : undefined,
        } satisfies StoredPhaseDefaults;
      })
      .filter(Boolean) as StoredPhaseDefaults[];
  } catch {
    return [];
  }
}

function storeUserPhaseDefaults(configs: PhaseConfig[]) {
  if (typeof window === 'undefined') return;
  const payload = configs.map((cfg) => ({
    slug: cfg.slug,
    model: cfg.model,
    tokens: cfg.tokens,
    prompt: cfg.prompt,
  }));
  try {
    window.localStorage.setItem('pipelinePhaseDefaults', JSON.stringify(payload));
  } catch (error) {
    console.error('Failed to persist pipeline phase defaults', error);
    throw error;
  }
}

function hasConfigDiff(current: PhaseConfig, base: PhaseConfig): boolean {
  const modelCurrent = (current.model || '').trim();
  const modelBase = (base.model || '').trim();
  const agentCurrent = (current.agentRole || '').trim();
  const agentBase = (base.agentRole || '').trim();
  const promptCurrent = (current.prompt || '').trim();
  const promptBase = (base.prompt || '').trim();
  if (modelCurrent !== modelBase) return true;
  if ((current.tokens ?? 0) !== (base.tokens ?? 0)) return true;
  if (agentCurrent !== agentBase) return true;
  if (promptCurrent !== promptBase) return true;
  return false;
}

function convertPhaseDefinitionToConfig(
  phase: PipelinePhaseDefaults | null,
  fallback: { id: string; title: string },
  templates: PromptTemplateRecord[],
): PhaseConfig {
  if (!phase) {
    return {
      phaseId: null,
      slug: fallback.id,
      name: fallback.title,
      model: '',
      tokens: 0,
      prompt: '',
      promptTemplateId: null,
      promptDefaultPath: null,
      promptTenantId: null,
      promptIsTenantDefault: false,
      isSystemPrompt: false,
      agentRole: null,
      isUpdatable: false,
    } satisfies PhaseConfig;
  }

  const promptKey = phase.prompt_template ?? null;
  const promptRecord = promptKey
    ? templates.find((tpl) => tpl.id === promptKey) ??
      templates.find((tpl) => tpl.default_path === promptKey) ??
      null
    : null;

  let slug = phase.slug;
  if (!slug || typeof slug !== 'string') {
    if (typeof phase.id === 'string' && phase.id) {
      slug = phase.id;
    } else {
      slug = fallback.id;
    }
  }

  const promptTemplateId = promptRecord?.id ?? (promptKey ?? null);
  const promptDefaultPath = promptRecord?.default_path ??
    (promptKey && /\.j2$/i.test(promptKey) ? promptKey : null);
  const promptTenantId = promptRecord?.tenant_id ?? null;
  const promptIsTenantDefault = Boolean(promptRecord?.is_tenant_default);
  // Falls der PromptRecord (noch) nicht geladen ist, bleibt der Content leer.
  // Der Editor lädt ihn ggf. on-demand über /templates/{default_path}.
  const promptContent =
    typeof promptRecord?.content === 'string' ? promptRecord.content : '';
  const isSystemPrompt = !promptTenantId && Boolean(promptTemplateId || promptDefaultPath);

  const tokensValue = Number(phase.tokens_plan_default ?? 0);
  const tokens = Number.isFinite(tokensValue) ? Math.max(0, Math.trunc(tokensValue)) : 0;

  return {
    // nur echte IDs sind speicherbar; andernfalls read‑only (z. B. ältere "release"‑Einträge)
    phaseId: phase?.id ? String(phase.id) : null,
    slug,
    name: phase.name ?? fallback.title,
    model: phase.model_name ?? '',
    tokens,
    prompt: promptContent,
    promptTemplateId,
    promptDefaultPath,
    promptTenantId,
    promptIsTenantDefault,
    isSystemPrompt,
    agentRole: phase.agent_role ?? null,
    isUpdatable: Boolean(phase?.id),
  } satisfies PhaseConfig;
}

function buildConfigsFromTemplate(
  template: PipelineTemplateSummary | null,
  templates: PromptTemplateRecord[],
): PhaseConfig[] {
  return PIPELINE_PHASES.filter((phase) => phase.id !== 'purpose').map((phase) => {
    const templatePhase = template?.phases.find(
      (entry) => entry.slug === phase.id || entry.id === phase.id,
    );
    return convertPhaseDefinitionToConfig(templatePhase ?? null, phase, templates);
  });
}

type TopTab = 'new' | 'list' | 'details';

async function delJson(path: string) {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) throw new Error(`DELETE ${path} failed`);
  try {
    return await res.json();
  } catch {
    return {};
  }
}

export function PurposePhaseContent(ctx: PhaseViewContext) {
  const purposes = ctx.purposes ?? [];
  const artifacts = (ctx.artifacts ?? []) as ArtifactItem[];
  const fetchPurposes = usePipelineStore((s) => s.fetchPurposes);
  const setSelectedPurpose = usePipelineStore((s) => s.setSelectedPurpose);
  const selectedPurposeId = ctx.selectedPurposeId ?? null;
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchBacklog = usePipelineStore((s) => s.fetchBacklog);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);

  const [tab, setTab] = useState<TopTab>('new');

  const [purposeName, setPurposeName] = useState('');
  const [mode, setMode] = useState<'manual' | 'auto'>('manual');
  const [templates, setTemplates] = useState<PipelineTemplateSummary[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateId, setTemplateId] = useState<string>('');

  const [promptTemplates, setPromptTemplates] =
    useState<PromptTemplateRecord[]>([]);
  const [phaseConfigs, setPhaseConfigs] = useState<PhaseConfig[]>([]);
  const [initialPhaseConfigs, setInitialPhaseConfigs] = useState<PhaseConfig[]>([]);
  const [phaseConfigsLoading, setPhaseConfigsLoading] = useState(false);
  const [savingPhaseSlug, setSavingPhaseSlug] = useState<string | null>(null);
  const [editingPhase, setEditingPhase] = useState<PhaseConfig | null>(null);
  const [editingPrompt, setEditingPrompt] = useState('');

  const [history, setHistory] = useState<any[]>([]);
  const lastLoadedPurposeRef = useRef<string | null>(null);

  const refreshPromptTemplates = useCallback(async () => {
    try {
      const data = await getJson<PromptTemplateListResponse>('/pipeline/prompts');
      const templatesList = Array.isArray(data?.templates) ? data.templates : [];
      setPromptTemplates(templatesList);
      return templatesList;
    } catch (error) {
      console.error('Failed to refresh prompt templates', error);
      return promptTemplates;
    }
  }, [promptTemplates]);

  const changedPhaseConfigs = useMemo(
    () =>
      phaseConfigs.filter((cfg) => {
        const base = initialPhaseConfigs.find((entry) => entry.slug === cfg.slug);
        return base ? hasConfigDiff(cfg, base) : false;
      }),
    [phaseConfigs, initialPhaseConfigs],
  );

  const changedPhaseSlugs = useMemo(
    () => new Set(changedPhaseConfigs.map((cfg) => cfg.slug)),
    [changedPhaseConfigs],
  );

  const maybeOfferUserDefaults = useCallback(() => {
    if (typeof window === 'undefined') return false;
    if (!changedPhaseConfigs.length) return false;
    const confirmed = window.confirm('Konfiguration als Benutzer-Standard speichern?');
    if (!confirmed) return false;
    try {
      storeUserPhaseDefaults(phaseConfigs);
      toast.success('Benutzer-Standard gespeichert.');
      return true;
    } catch {
      toast.error('Benutzer-Standard konnte nicht gespeichert werden.');
      return false;
    }
  }, [changedPhaseConfigs, phaseConfigs]);

  const persistPhaseConfiguration = useCallback(
    async (
      purposeId: string,
      config: PhaseConfig,
      baseConfig: PhaseConfig,
    ): Promise<{
      phase: PipelinePhaseDefaults | null;
      promptChanged: boolean;
      promptTemplateId: string | null;
    }> => {
      const updates: Record<string, unknown> = {
        purpose_id: purposeId,
        scope: 'purpose',
      };

      // Wenn die Phase im Template keine echte ID hat, ist sie nicht update-fähig.
      if (!config.isUpdatable || !config.phaseId) {
        return { phase: null, promptChanged: false, promptTemplateId: config.promptTemplateId ?? null };
      }

      const normalizedModel = (config.model || '').trim();
      const baseModel = (baseConfig.model || '').trim();
      if (normalizedModel !== baseModel) {
        updates.model_name = normalizedModel || null;
      }

      if ((config.tokens ?? 0) !== (baseConfig.tokens ?? 0)) {
        const sanitizedTokens = Math.max(0, Math.trunc(Number(config.tokens) || 0));
        updates.tokens_plan_default = sanitizedTokens;
      }

      const agentCurrent = (config.agentRole || '').trim();
      const agentBase = (baseConfig.agentRole || '').trim();
      if (agentCurrent !== agentBase) {
        updates.agent_role = agentCurrent || null;
      }

      const promptCurrent = (config.prompt || '').trim();
      const promptBase = (baseConfig.prompt || '').trim();
      let promptTemplateId: string | null | undefined = baseConfig.promptTemplateId ?? null;
      let promptChanged = false;

      if (promptCurrent !== promptBase) {
        promptChanged = true;
        if (!promptCurrent) {
          promptTemplateId = null;
        } else if (
          config.promptTemplateId &&
          config.promptTenantId &&
          !config.promptIsTenantDefault
        ) {
          await putJson(`/pipeline/prompts/update/${config.promptTemplateId}`, {
            content: promptCurrent,
          });
          promptTemplateId = config.promptTemplateId;
        } else {
          const created = await postJson<{ id: string }>('/pipeline/prompts/create', {
            phase_slug: config.slug,
            content: promptCurrent,
            agent: agentCurrent || null,
          });
          promptTemplateId = created?.id ?? null;
        }
      } else {
        promptTemplateId = config.promptTemplateId ?? baseConfig.promptTemplateId ?? null;
      }

      if (
        promptChanged ||
        (promptTemplateId ?? null) !== (baseConfig.promptTemplateId ?? null)
      ) {
        updates.prompt_template = promptTemplateId ?? null;
      }

      const updateKeys = Object.keys(updates).filter(
        (key) => key !== 'purpose_id' && key !== 'scope',
      );
      if (!updateKeys.length) {
        return {
          phase: null,
          promptChanged: false,
          promptTemplateId: promptTemplateId ?? null,
        };
      }

      const response = await putJson<{ template: PipelineTemplateSummary }>(
        `/pipeline/phases/${config.phaseId}`, // garantiert echte ID, siehe Guard oben
        updates,
      );
      const template = (response && response.template) ? response.template : null;
      const updatedPhase = template?.phases.find(
        (phase) => phase.slug === config.slug || phase.id === config.phaseId,
      ) ?? null;

      return {
        phase: updatedPhase ?? null,
        promptChanged,
        promptTemplateId: promptTemplateId ?? null,
      };
    },
    [],
  );

  const savePhaseConfig = useCallback(
    async (
      purposeId: string,
      config: PhaseConfig,
      baseConfig: PhaseConfig,
    ) => {
      const result = await persistPhaseConfiguration(
        purposeId,
        config,
        baseConfig,
      );
      let promptList: PromptTemplateRecord[] | undefined;
      if (result.promptChanged) {
        promptList = await refreshPromptTemplates();
      }

      const nextConfig = result.phase
        ? convertPhaseDefinitionToConfig(
            result.phase,
            { id: config.slug, title: config.name },
            promptList ?? promptTemplates,
          )
        : {
            ...config,
            promptTemplateId: result.promptTemplateId,
          };

      setPhaseConfigs((prev) =>
        prev.map((entry) => (entry.slug === config.slug ? nextConfig : entry)),
      );
      setInitialPhaseConfigs((prev) =>
        prev.map((entry) => (entry.slug === config.slug ? nextConfig : entry)),
      );

      await fetchGraphAndStatus(purposeId);
      await fetchBacklog();

      return nextConfig;
    },
    [
      persistPhaseConfiguration,
      refreshPromptTemplates,
      promptTemplates,
      fetchGraphAndStatus,
      fetchBacklog,
    ],
  );

  const selectedPurpose =
    purposes.find((p: any) => p.id === selectedPurposeId) ?? null;

  const released = artifacts.filter((a) => a.released);
  const drafts = artifacts.filter((a) => !a.released);

  useEffect(() => {
    let active = true;
    setTemplatesLoading(true);
    getJson<PipelineTemplateSummary[]>('/pipeline/templates')
      .then((data) => active && setTemplates(Array.isArray(data) ? data : []))
      .catch(() => active && setTemplates([]))
      .finally(() => active && setTemplatesLoading(false));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    getJson<PromptTemplateListResponse>('/pipeline/prompts')
      .then((data) => {
        if (!active) return;
        const templatesList = Array.isArray(data?.templates) ? data.templates : [];
        setPromptTemplates(templatesList);
      })
      .catch(() => {
        if (!active) return;
        setPromptTemplates([]);
      });
    return () => {
      active = false;
    };
  }, []);

  const defaultTemplateId = useMemo(() => {
    if (!templates.length) return '';
    const tTenant = templates.find((t) => t.is_default && t.tenant_id);
    if (tTenant) return tTenant.id;
    const tGlobal = templates.find((t) => t.is_default);
    return (tGlobal ?? templates[0]).id;
  }, [templates]);

  useEffect(() => {
    if (!templateId && defaultTemplateId) {
      setTemplateId(defaultTemplateId);
    }
  }, [templateId, defaultTemplateId]);

  useEffect(() => {
    if (tab !== 'new') return;
    const activeTemplateId = templateId || defaultTemplateId;
    const template = templates.find((entry) => entry.id === activeTemplateId) ?? null;
    const baseConfigs = buildConfigsFromTemplate(template ?? null, promptTemplates);
    setInitialPhaseConfigs(baseConfigs);

    const storedDefaults = loadUserPhaseDefaults();
    if (!storedDefaults.length) {
      setPhaseConfigs(baseConfigs);
      return;
    }

    const merged = baseConfigs.map((cfg) => {
      const stored = storedDefaults.find((entry) => entry.slug === cfg.slug);
      if (!stored) return cfg;
      const tokensValue = Number(stored.tokens);
      const tokens = Number.isFinite(tokensValue)
        ? Math.max(0, Math.trunc(tokensValue))
        : cfg.tokens;
      const next: PhaseConfig = {
        ...cfg,
        model: typeof stored.model === 'string' ? stored.model : cfg.model,
        tokens,
        prompt: typeof stored.prompt === 'string' ? stored.prompt : cfg.prompt,
      };
      if (typeof stored.prompt === 'string' && stored.prompt.trim()) {
        next.isSystemPrompt = false;
        next.promptTemplateId = null;
        next.promptTenantId = null;
        next.promptIsTenantDefault = false;
      }
      return next;
    });
    setPhaseConfigs(merged);
  }, [tab, templateId, defaultTemplateId, templates, promptTemplates]);

  useEffect(() => {
    if (!selectedPurposeId) return;
    fetchArtifacts();
    fetchBacklog();
    fetchGraphAndStatus(selectedPurposeId);
    const controller = new AbortController();
    const signal = controller.signal;
    getJson<any>(`/purposes/${selectedPurposeId}/status`, { signal })
      .then((rows) => setHistory(Array.isArray(rows) ? rows : []))
      .catch(() => setHistory([]));
    const iv = setInterval(() => {
      fetchArtifacts();
      fetchGraphAndStatus(selectedPurposeId);
    }, 6000);
    return () => {
      controller.abort();
      clearInterval(iv);
    };
  }, [selectedPurposeId, fetchArtifacts, fetchBacklog, fetchGraphAndStatus]);

  useEffect(() => {
    if (editingPhase && typeof editingPhase.prompt === 'string') {
      setEditingPrompt(editingPhase.prompt);
    } else {
      setEditingPrompt('');
    }
  }, [editingPhase]);

  useEffect(() => {
    if (tab !== 'details' || !selectedPurposeId) return;

    const samePurpose = lastLoadedPurposeRef.current === selectedPurposeId;
    if (samePurpose && changedPhaseConfigs.length > 0) {
      return;
    }

    let active = true;
    setPhaseConfigsLoading(true);
    getJson<{ template: PipelineTemplateSummary }>(
      `/purposes/${selectedPurposeId}/pipeline`,
    )
      .then((data) => {
        if (!active) return;
        const template = data?.template ?? null;
        const configs = buildConfigsFromTemplate(template, promptTemplates);
        setInitialPhaseConfigs(configs);
        setPhaseConfigs(configs);
        lastLoadedPurposeRef.current = selectedPurposeId;
      })
      .catch(() => {
        if (!active) return;
        setInitialPhaseConfigs([]);
        setPhaseConfigs([]);
      })
      .finally(() => {
        if (!active) return;
        setPhaseConfigsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [
    tab,
    selectedPurposeId,
    promptTemplates,
    changedPhaseConfigs.length,
  ]);

  const handleCreate = useCallback(async () => {
    const name = purposeName.trim();
    if (!name) {
      toast.error('Bitte gib ein Projektziel ein.');
      return;
    }

    maybeOfferUserDefaults();

    const ok = await ctx.onCreatePurpose?.(name, templateId || undefined);
    if (ok) {
      const newPurposeId = usePipelineStore.getState().selectedPurposeId;
      if (newPurposeId && changedPhaseConfigs.length) {
        let promptsRefreshed = false;
        let updateFailed = false;
        for (const cfg of phaseConfigs) {
          const base = initialPhaseConfigs.find((entry) => entry.slug === cfg.slug);
          if (!base || !hasConfigDiff(cfg, base)) continue;
          try {
            const result = await persistPhaseConfiguration(newPurposeId, cfg, base);
            if (result.promptChanged && !promptsRefreshed) {
              await refreshPromptTemplates();
              promptsRefreshed = true;
            }
          } catch (error) {
            console.error('Failed to persist phase configuration', error);
            updateFailed = true;
          }
        }
        if (updateFailed) {
          toast.error('Einige Phaseneinstellungen konnten nicht übernommen werden.');
        }
      }

      try {
        const token = localStorage.getItem('token');
        const id = usePipelineStore.getState().selectedPurposeId;
        if (mode !== 'manual' && id) {
          await fetch(`${API_BASE}/purposes/${id}`, {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ mode }),
          });
        }
      } catch {
        /* ignore */
      }

      setPurposeName('');
      setMode('manual');
      setTemplateId(defaultTemplateId || '');
      setTab('details');
      fetchPurposes();
    }
  }, [
    purposeName,
    mode,
    templateId,
    ctx.onCreatePurpose,
    maybeOfferUserDefaults,
    changedPhaseConfigs,
    phaseConfigs,
    initialPhaseConfigs,
    persistPhaseConfiguration,
    refreshPromptTemplates,
    fetchPurposes,
    defaultTemplateId,
  ]);

  const handleStart = useCallback(
    async (id: string) => {
      if (id === selectedPurposeId) {
        maybeOfferUserDefaults();
      }
      try {
        await postJson(`/purposes/${id}/start`, {});
        toast.success('Gestartet.');
        if (id === selectedPurposeId) {
          await fetchGraphAndStatus(id);
        }
      } catch {
        toast.error('Start fehlgeschlagen.');
      }
    },
    [selectedPurposeId, fetchGraphAndStatus, maybeOfferUserDefaults],
  );

  const handlePause = useCallback(
    async (id: string) => {
      try {
        await postJson(`/purposes/${id}/pause`, {});
        toast.success('Pausiert.');
        if (id === selectedPurposeId) {
          await fetchGraphAndStatus(id);
        }
      } catch {
        toast.error('Pause fehlgeschlagen.');
      }
    },
    [selectedPurposeId, fetchGraphAndStatus],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      if (!confirm('Dieses Projektziel endgültig löschen?')) return;
      try {
        await delJson(`/purposes/${id}`);
        toast.success('Gelöscht.');
        if (id === selectedPurposeId) {
          usePipelineStore.setState({
            selectedPurposeId: null,
            selectedArtifactId: null,
            artifactContent: '',
            feedbacks: [],
          });
          setTab('list');
        }
        await fetchPurposes();
      } catch {
        toast.error('Löschen fehlgeschlagen.');
      }
    },
    [selectedPurposeId, fetchPurposes],
  );

  const downloadArtifactFile = (artifactId: string, filename: string) => {
    const token = localStorage.getItem('token');
    fetch(`${API_BASE}/artifact/${artifactId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error('Download fehlgeschlagen');
        return res.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(() => toast.error('Download fehlgeschlagen'));
  };

  const openPromptEditor = useCallback(
    async (slug: string) => {
      const cfg = phaseConfigs.find((entry) => entry.slug === slug);
      if (!cfg) return;
      // System-Prompt ohne geladenen Inhalt? -> on-demand laden
      if (cfg.isSystemPrompt && !cfg.prompt && cfg.promptDefaultPath) {
        const text = await fetchTemplateText(cfg.promptDefaultPath);
        if (text) {
          // UI-Status aktualisieren (Anzeige) – bleibt trotzdem "System (read-only)"
          setPhaseConfigs((prev) =>
            prev.map((e) => (e.slug === slug ? { ...e, prompt: text } : e)),
          );
          setEditingPhase({ ...cfg, prompt: text });
          setEditingPrompt(text);
          return;
        }
      }
      setEditingPhase(cfg);
    },
    [phaseConfigs],
  );

  const closePromptEditor = useCallback(() => {
    setEditingPhase(null);
  }, []);

  const makePromptEditable = useCallback(() => {
    if (!editingPhase) return;
    const updated: PhaseConfig = {
      ...editingPhase,
      isSystemPrompt: false,
      promptTemplateId: null,
      promptTenantId: null,
      promptIsTenantDefault: false,
    };
    setPhaseConfigs((prev) =>
      prev.map((entry) => (entry.slug === updated.slug ? updated : entry)),
    );
    setEditingPhase(updated);
  }, [editingPhase]);

  const handlePromptModalSave = useCallback(() => {
    if (!editingPhase) return;
    const trimmed = editingPrompt;
    const updated: PhaseConfig = { ...editingPhase, prompt: trimmed };
    setPhaseConfigs((prev) =>
      prev.map((entry) => (entry.slug === updated.slug ? updated : entry)),
    );
    setEditingPhase(null);
  }, [editingPhase, editingPrompt]);

  const updatePhaseConfigValue = useCallback(
    (slug: string, patch: Partial<PhaseConfig>) => {
      setPhaseConfigs((prev) =>
        prev.map((entry) => (entry.slug === slug ? { ...entry, ...patch } : entry)),
      );
    },
    [],
  );

  function renderPhaseOverview(mode: 'new' | 'details') {
    const isDetails = mode === 'details';
    const isLoading = isDetails && phaseConfigsLoading;

    return (
      <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Phasenübersicht
          </h3>
          {isDetails && isLoading && (
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Lade Konfiguration …
            </span>
          )}
        </div>
        {!phaseConfigs.length && !isLoading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Keine Phasen gefunden.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">Phase</th>
                  <th className="px-3 py-2 text-left font-semibold">Modell</th>
                  <th className="px-3 py-2 text-left font-semibold">Token-Limit</th>
                  <th className="px-3 py-2 text-left font-semibold">Agent-Rolle(n)</th>
                  <th className="px-3 py-2 text-left font-semibold">Prompt</th>
                  {isDetails && (
                    <th className="px-3 py-2 text-left font-semibold">Aktionen</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {phaseConfigs.map((cfg) => {
                  const rowDisabled = isDetails && (isLoading || savingPhaseSlug === cfg.slug);
                  const hasChanges = changedPhaseSlugs.has(cfg.slug);
                  return (
                    <tr key={cfg.slug} className="text-slate-700 dark:text-slate-200">
                      <td className="px-3 py-2">{cfg.name}</td>
                      <td className="px-3 py-2">
                        <select
                          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                          value={cfg.model}
                          disabled={rowDisabled}
                          onChange={(e) =>
                            updatePhaseConfigValue(cfg.slug, { model: e.target.value })
                          }
                        >
                          {MODEL_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="number"
                          min={0}
                          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                          value={cfg.tokens}
                          disabled={rowDisabled}
                          onChange={(e) => {
                            const next = Math.max(0, Math.trunc(Number(e.target.value) || 0));
                            updatePhaseConfigValue(cfg.slug, { tokens: next });
                          }}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                          value={cfg.agentRole || ''}
                          disabled={rowDisabled}
                          onChange={(e) =>
                            updatePhaseConfigValue(cfg.slug, { agentRole: e.target.value })
                          }
                        />
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col gap-2">
                          <div className="flex items-start justify-between gap-2">
                            <span className="line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
                              {cfg.prompt ? cfg.prompt : 'Kein Prompt hinterlegt.'}
                            </span>
                            <span
                              className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                                cfg.isSystemPrompt
                                  ? 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                                  : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                              }`}
                            >
                              {cfg.isSystemPrompt ? 'System' : 'Custom'}
                            </span>
                          </div>
                          <button
                            type="button"
                            className="self-start text-xs font-semibold text-amber-600 hover:text-amber-500"
                            onClick={() => openPromptEditor(cfg.slug)}
                            disabled={rowDisabled}
                          >
                            Prompt {cfg.isSystemPrompt ? 'ansehen' : 'bearbeiten'}
                          </button>
                        </div>
                      </td>
                      {isDetails && (
                        <td className="px-3 py-2">
                          <button
                            type="button"
                              onClick={() => handleSavePhaseRow(cfg.slug)}
                              disabled={!cfg.isUpdatable || !hasChanges || rowDisabled}
                              title={
                                cfg.isUpdatable ? undefined : 'Diese Phase ist im aktiven Template nicht update-fähig.'
                              }
                              className={`rounded-md px-3 py-1.5 text-xs font-semibold text-white ${
                                !cfg.isUpdatable || !hasChanges || rowDisabled
                                  ? 'bg-slate-400 dark:bg-slate-600'
                                  : 'bg-emerald-600 hover:bg-emerald-700'
                              }`}
                          >
                            {savingPhaseSlug === cfg.slug ? 'Speichern…' : 'Speichern'}
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    );
  }

  /**
   * Speichert die Konfiguration einer einzelnen Phase,
   * falls sich Änderungen gegenüber dem initialen Wert ergeben haben.
   */
  const handleSavePhaseRow = useCallback(
    async (slug: string) => {
      if (!selectedPurposeId) return;
      const config = phaseConfigs.find((cfg) => cfg.slug === slug);
      const base = initialPhaseConfigs.find((cfg) => cfg.slug === slug);
      if (!config || !base) return;
      if (!config.isUpdatable || !config.phaseId) {
        toast('Diese Phase kann in der aktuellen Vorlage nicht aktualisiert werden.');
        return;
      }
      if (!hasConfigDiff(config, base)) {
        toast('Keine Änderungen für diese Phase.');
        return;
      }

      maybeOfferUserDefaults();
      setSavingPhaseSlug(slug);
      try {
        await savePhaseConfig(selectedPurposeId, config, base);
        toast.success(`Phase "${config.name}" gespeichert.`);
      } catch (error) {
        console.error('Failed to save phase configuration', slug, error);
        // Backend meldet z. B. 500, wenn eine unbekannte Phase-ID angesprochen wird.
        // Mit den Guards oben sollte das nicht mehr passieren; falls doch:
        toast.error(
          'Phase konnte nicht aktualisiert werden. Prüfe die Template‑Phase und ihre ID.',
        );
        toast.error('Phase konnte nicht aktualisiert werden.');
      } finally {
        setSavingPhaseSlug(null);
      }
    },
    [
      selectedPurposeId,
      phaseConfigs,
      initialPhaseConfigs,
      maybeOfferUserDefaults,
      savePhaseConfig,
    ],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {(['new', 'list', 'details'] as TopTab[]).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              tab === key
                ? 'bg-amber-500 text-white'
                : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'
            }`}
          >
            {key === 'new' && 'Neu'}
            {key === 'list' && 'Liste'}
            {key === 'details' && 'Details'}
          </button>
        ))}
      </div>

      {tab === 'new' && (
        <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Projektziel / Zweck
              </label>
              <input
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                placeholder="Beschreibe kurz dein Ziel …"
                value={purposeName}
                onChange={(e) => setPurposeName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Modus
              </label>
              <select
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                value={mode}
                onChange={(e) => setMode(e.target.value as 'manual' | 'auto')}
              >
                <option value="manual">Manuell</option>
                <option value="auto">Automatisch</option>
              </select>
            </div>
            <div className="md:col-span-3">
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Pipeline‑Vorlage
              </label>
              <select
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                disabled={templatesLoading}
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
              >
                {(templates ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} {t.is_default ? '• Standard' : ''}
                  </option>
                ))}
                {!templates.length && <option value="">Keine Vorlagen verfügbar</option>}
              </select>
            </div>
          </div>
          {renderPhaseOverview('new')}
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
            >
              Anlegen
            </button>
          </div>
        </section>
      )}

      {tab === 'list' && (
        <section className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Projektziel</th>
                <th className="px-3 py-2 text-left font-semibold">Modus</th>
                <th className="px-3 py-2 text-left font-semibold">Erstellt</th>
                <th className="px-3 py-2 text-left font-semibold">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {(purposes as any[]).map((p) => (
                <tr key={p.id} className="text-slate-700 dark:text-slate-200">
                  <td className="px-3 py-2">{p.purpose ?? p.name ?? '—'}</td>
                  <td className="px-3 py-2 uppercase">{(p.mode ?? 'manual').toString()}</td>
                  <td className="px-3 py-2">
                    {p.created_at ? new Date(p.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        className="inline-flex items-center gap-1 rounded bg-amber-500 px-2 py-1 text-xs font-semibold text-white hover:bg-amber-600"
                        onClick={() => {
                          setSelectedPurpose(p.id);
                          setTab('details');
                        }}
                        title="Öffnen"
                      >
                        <ChevronRight className="h-3 w-3" /> Öffnen
                      </button>
                      <button
                        className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
                        onClick={() => handleStart(p.id)}
                        title="Start"
                      >
                        <PlayCircle className="h-3 w-3" /> Start
                      </button>
                      <button
                        className="inline-flex items-center gap-1 rounded bg-slate-600 px-2 py-1 text-xs font-semibold text-white hover:bg-slate-700"
                        onClick={() => handlePause(p.id)}
                        title="Pause"
                      >
                        <PauseCircle className="h-3 w-3" /> Pause
                      </button>
                      <button
                        className="inline-flex items-center gap-1 rounded bg-rose-600 px-2 py-1 text-xs font-semibold text-white hover:bg-rose-700"
                        onClick={() => handleDelete(p.id)}
                        title="Löschen"
                      >
                        <Trash2 className="h-3 w-3" /> Löschen
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {(!purposes || (purposes as any[]).length === 0) && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-500">
                    Noch keine Projektziele vorhanden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}

      {tab === 'details' && (
        <section className="space-y-6">
          {!selectedPurpose ? (
            <p className="text-sm text-slate-500">Bitte in der Liste ein Projektziel auswählen.</p>
          ) : (
            <>
              <div className="flex flex-col justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900 md:flex-row md:items-center">
                <div>
                  <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                    {selectedPurpose.purpose ?? selectedPurpose.name ?? 'Projektziel'}
                  </h2>
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    Modus: <b>{selectedPurpose.mode ?? 'manual'}</b>{' '}
                    {selectedPurpose.created_at && (
                      <>· {new Date(selectedPurpose.created_at).toLocaleString()}</>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="inline-flex items-center gap-1 rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                    onClick={() => handleStart(selectedPurpose.id)}
                  >
                    <PlayCircle className="h-3 w-3" /> Starten
                  </button>
                  <button
                    className="inline-flex items-center gap-1 rounded bg-slate-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
                    onClick={() => handlePause(selectedPurpose.id)}
                  >
                    <PauseCircle className="h-3 w-3" /> Pausieren
                  </button>
                  <button
                    className="inline-flex items-center gap-1 rounded bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
                    onClick={() => handleDelete(selectedPurpose.id)}
                  >
                    <Trash2 className="h-3 w-3" /> Löschen
                  </button>
                </div>
              </div>

              {renderPhaseOverview('details')}

              <div className="grid gap-4 md:grid-cols-2">
                <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                  <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                    Aktuelle Artefakte (released)
                  </h3>
                  <ul className="space-y-2 text-sm">
                    {released.map((a) => (
                      <li
                        key={a.id}
                        className="flex items-center justify-between rounded border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                      >
                        <span className="truncate text-emerald-600">
                          {a.repo_path?.replace(/^[^/]+\//, '')}
                        </span>
                        <button
                          className="text-xs font-semibold text-amber-600 hover:underline"
                          onClick={() =>
                            downloadArtifactFile(
                              a.id,
                              a.repo_path?.split('/').pop() || a.id,
                            )
                          }
                        >
                          Download
                        </button>
                      </li>
                    ))}
                    {released.length === 0 && (
                      <li className="text-slate-500">Keine freigegebenen Artefakte.</li>
                    )}
                  </ul>
                </section>
                <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                  <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                    Entwürfe (draft)
                  </h3>
                  <ul className="space-y-2 text-sm">
                    {drafts.map((a) => (
                      <li
                        key={a.id}
                        className="flex items-center justify-between rounded border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                      >
                        <span className="truncate text-slate-700 dark:text-slate-200">
                          {a.repo_path?.replace(/^[^/]+\//, '')}
                        </span>
                        <span className="text-xs text-slate-500">draft</span>
                      </li>
                    ))}
                    {drafts.length === 0 && (
                      <li className="text-slate-500">Keine Entwürfe vorhanden.</li>
                    )}
                  </ul>
                </section>
              </div>

              <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                  Verlauf
                </h3>
                <ul className="space-y-1 text-sm">
                  {(history ?? []).map((row: any, idx: number) => (
                    <li key={idx} className="text-slate-600 dark:text-slate-300">
                      <span className="mr-2 inline-block rounded bg-slate-200 px-2 py-0.5 text-xs dark:bg-slate-700">
                        {row.status ?? row.state ?? 'status'}
                      </span>
                      {row.message ?? row.detail ?? ''}
                      {row.timestamp && (
                        <span className="ml-2 text-xs text-slate-400">
                          {new Date(row.timestamp).toLocaleString()}
                        </span>
                      )}
                    </li>
                  ))}
                  {(!history || history.length === 0) && (
                    <li className="text-slate-500">Noch kein Verlauf vorhanden.</li>
                  )}
                </ul>
              </section>
            </>
          )}
        </section>
      )}

      {editingPhase && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                Prompt für {editingPhase.name}
              </h3>
              <button
                type="button"
                className="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                onClick={closePromptEditor}
              >
                ×
              </button>
            </div>
            {editingPhase.isSystemPrompt && (
              <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-500/60 dark:bg-amber-500/10 dark:text-amber-200">
                Systemvorlagen sind schreibgeschützt. Erstelle eine Kopie, um Anpassungen vorzunehmen.
                <button
                  type="button"
                  className="ml-2 rounded bg-amber-500 px-2 py-1 text-xs font-semibold text-white hover:bg-amber-600"
                  onClick={makePromptEditable}
                >
                  Duplizieren &amp; bearbeiten
                </button>
              </div>
            )}
            <textarea
              rows={12}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100"
              value={editingPrompt}
              onChange={(e) => setEditingPrompt(e.target.value)}
              readOnly={editingPhase.isSystemPrompt}
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={closePromptEditor}
                className="rounded-md bg-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-300 dark:bg-slate-700 dark:text-slate-200 dark:hover:bg-slate-600"
              >
                Abbrechen
              </button>
              <button
                type="button"
                onClick={handlePromptModalSave}
                disabled={editingPhase.isSystemPrompt}
                className={`rounded-md px-4 py-2 text-sm font-medium text-white ${
                  editingPhase.isSystemPrompt
                    ? 'bg-slate-400 dark:bg-slate-600'
                    : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                Übernehmen
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function PurposePhaseSidebar() {
  return (
    <aside className="text-sm text-slate-600 dark:text-slate-300">
      <p className="mb-1 font-medium">Projektziel</p>
      <p>Lege ein Ziel an (Neu), verwalte Ziele (Liste) oder öffne Details.</p>
    </aside>
  );
}
