import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type ComponentType,
  type LazyExoticComponent,
  Suspense,
  lazy,
} from 'react';
import Editor from '@monaco-editor/react';
import {
  CheckCircle2,
  CircleDashed,
  Clock3,
  History,
  Package,
  PauseCircle,
  PlayCircle,
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import usePipelineStore from '../store/pipelineStore';
import PurposeSelector from '../components/PurposeSelector';
import ArtifactSection from '../components/ArtifactSection';
import GraphSection from '../components/GraphSection';
import { API_BASE, getJson, postJson, putJson } from '../lib/api';
import { normalizeAgentValue, normalizePromptContent } from '../lib/prompts';
import { PIPELINE_PHASES, PHASE_DESCRIPTIONS, type PhaseId } from '../components/pipeline/phaseConfig';
import PhaseNavigation from '../components/pipeline/PhaseNavigation';
import type {
  ArtifactItem,
  PhaseNavItem,
  PhaseViewContext,
  PipelinePhaseDefaults,
  PipelineTemplateSummary,
  PromptAssignmentSummary,
  PromptTemplateListResponse,
  PromptTemplateRecord,
} from '../components/pipeline/types';

function createLazyPhaseComponent<
  TModule extends Record<string, ComponentType<PhaseViewContext>>,
  TExport extends keyof TModule,
>(
  loader: () => Promise<TModule>,
  exportName: TExport,
): LazyExoticComponent<ComponentType<PhaseViewContext>> {
  return lazy(async () => {
    const module = await loader();
    const Component = module[exportName];

    if (!Component) {
      throw new Error(`Phase component "${String(exportName)}" could not be loaded.`);
    }

    return { default: Component };
  });
}

const LazyPurposePhaseContent = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/PurposePhase'),
  'PurposePhaseContent',
);
const LazyPurposePhaseSidebar = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/PurposePhase'),
  'PurposePhaseSidebar',
);
const LazyVisionPhaseContent = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/VisionPhase'),
  'VisionPhaseContent',
);
const LazyVisionPhaseSidebar = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/VisionPhase'),
  'VisionPhaseSidebar',
);
const LazyPrdPhaseContent = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/PrdPhase'),
  'PrdPhaseContent',
);
const LazyPrdPhaseSidebar = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/PrdPhase'),
  'PrdPhaseSidebar',
);
const LazyArchitecturePhaseContent = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ArchitecturePhase'),
  'ArchitecturePhaseContent',
);
const LazyArchitecturePhaseSidebar = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ArchitecturePhase'),
  'ArchitecturePhaseSidebar',
);
const LazyArchitectureReviewPhaseContent = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ArchitectureReviewPhase'),
  'ArchitectureReviewPhaseContent',
);
const LazyArchitectureReviewPhaseSidebar = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ArchitectureReviewPhase'),
  'ArchitectureReviewPhaseSidebar',
);
const LazyImplementationPhaseContent = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ImplementationPhase'),
  'ImplementationPhaseContent',
);
const LazyImplementationPhaseSidebar = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ImplementationPhase'),
  'ImplementationPhaseSidebar',
);
const LazyReviewPhaseContent = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ReviewPhase'),
  'ReviewPhaseContent',
);
const LazyReviewPhaseSidebar = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ReviewPhase'),
  'ReviewPhaseSidebar',
);
const LazyReleasePhaseContent = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ReleasePhase'),
  'ReleasePhaseContent',
);
const LazyReleasePhaseSidebar = createLazyPhaseComponent(
  () => import('../components/pipeline/phases/ReleasePhase'),
  'ReleasePhaseSidebar',
);

console.log('Loading PipelineView module');

interface PhaseMeta {
  id: PhaseId;
  title: string;
  icon: (typeof PIPELINE_PHASES)[number]['icon'];
  completed: boolean;
  index: number;
  isCurrent: boolean;
  isUpcoming: boolean;
}

const PHASE_ORDER: PhaseId[] = PIPELINE_PHASES.map((phase) => phase.id);

const PHASE_TO_TEMPLATE_SLUG: Partial<Record<PhaseId, string>> = {
  vision: 'vision',
  prd: 'prd',
  architecture: 'architecture',
  architecture_review: 'architecture_review',
  implementation: 'implementation',
};

const MODEL_OPTIONS = [
  { value: '', label: 'Standard übernehmen' },
  { value: 'gpt-4', label: 'GPT-4' },
  { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
  { value: 'claude-3-opus', label: 'Claude 3 Opus' },
];

const SCOPE_OPTIONS: { value: 'purpose' | 'tenant_default' | 'template'; label: string }[] = [
  { value: 'purpose', label: 'Nur dieses Projekt' },
  { value: 'tenant_default', label: 'Als Mandanten-Standard speichern' },
  { value: 'template', label: 'Vorlage aktualisieren' },
];

const PHASE_CONTENT_COMPONENTS: Record<
  PhaseId,
  LazyExoticComponent<ComponentType<PhaseViewContext>>
> = {
  purpose: LazyPurposePhaseContent,
  vision: LazyVisionPhaseContent,
  prd: LazyPrdPhaseContent,
  architecture: LazyArchitecturePhaseContent,
  architecture_review: LazyArchitectureReviewPhaseContent,
  implementation: LazyImplementationPhaseContent,
  review: LazyReviewPhaseContent,
  release: LazyReleasePhaseContent,
};

const PHASE_SIDEBAR_COMPONENTS: Record<
  PhaseId,
  LazyExoticComponent<ComponentType<PhaseViewContext>>
> = {
  purpose: LazyPurposePhaseSidebar,
  vision: LazyVisionPhaseSidebar,
  prd: LazyPrdPhaseSidebar,
  architecture: LazyArchitecturePhaseSidebar,
  architecture_review: LazyArchitectureReviewPhaseSidebar,
  implementation: LazyImplementationPhaseSidebar,
  review: LazyReviewPhaseSidebar,
  release: LazyReleasePhaseSidebar,
};

export default function PipelineView() {
  const artifacts = usePipelineStore((s) => s.artifacts) as ArtifactItem[];
  const backlog = usePipelineStore((s) => s.backlog);
  const purposes = usePipelineStore((s) => (s as any).purposes ?? []);
  const graphNodes = usePipelineStore((s) => s.graphNodes);
  const graphEdges = usePipelineStore((s) => s.graphEdges);
  const tasksStatus = usePipelineStore((s) => s.tasksStatus);
  const paused = usePipelineStore((s) => s.paused);
  const isLoading = usePipelineStore((s) => s.isLoading);
  const error = usePipelineStore((s) => s.error);
  const budgetLeft = usePipelineStore((s) => s.budgetLeft);
  const budgetTotal = usePipelineStore((s) => s.budgetTotal);
  const selectedPurposeId = usePipelineStore((s) => s.selectedPurposeId);
  const fetchPurposes = usePipelineStore((s) => s.fetchPurposes);
  const setSelectedPurpose = usePipelineStore((s) => s.setSelectedPurpose);
  const fetchArtifacts = usePipelineStore((s) => s.fetchArtifacts);
  const fetchBacklog = usePipelineStore((s) => s.fetchBacklog);
  const fetchGraphAndStatus = usePipelineStore((s) => s.fetchGraphAndStatus);

  const [allowResearch, setAllowResearch] = useState<boolean | null>(null);
  const [updatingResearch, setUpdatingResearch] = useState(false);
  const [creatingPurpose, setCreatingPurpose] = useState(false);
  const [templates, setTemplates] = useState<PipelineTemplateSummary[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [currentTemplate, setCurrentTemplate] = useState<PipelineTemplateSummary | null>(null);
  const [loadingPipeline, setLoadingPipeline] = useState(false);
  const [phaseScope, setPhaseScope] = useState<'purpose' | 'tenant_default' | 'template'>('purpose');
  const [phaseModel, setPhaseModel] = useState('');
  const [phaseTokens, setPhaseTokens] = useState('');
  const [phasePrompt, setPhasePrompt] = useState('');
  const [phaseSaving, setPhaseSaving] = useState(false);
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplateRecord[]>([]);
  const [promptAssignments, setPromptAssignments] = useState<PromptAssignmentSummary[]>([]);
  const [promptTemplatesLoading, setPromptTemplatesLoading] = useState(false);
  const [autoPipeline, setAutoPipeline] = useState(false);

  const toggleAutoPipeline = useCallback(() => {
    setAutoPipeline((prev) => !prev);
  }, []);

  const defaultTemplateId = useMemo(() => {
    if (!templates.length) return null;
    const tenantDefault = templates.find((tpl) => tpl.is_default && tpl.tenant_id);
    if (tenantDefault) return tenantDefault.id;
    const globalDefault = templates.find((tpl) => tpl.is_default);
    return (globalDefault ?? templates[0]).id;
  }, [templates]);

  useEffect(() => {
    fetchPurposes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchPurposes]);

  useEffect(() => {
    let active = true;
    getJson<{ allow_web_research: boolean }>('/settings/research')
      .then((data) => {
        if (!active) return;
        setAllowResearch(Boolean(data?.allow_web_research));
      })
      .catch(() => {
        if (!active) return;
        setAllowResearch(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setTemplatesLoading(true);
    getJson<PipelineTemplateSummary[]>('/pipeline/templates')
      .then((data) => {
        if (!active) return;
        const list = Array.isArray(data) ? data : [];
        setTemplates(list);
      })
      .catch(() => {
        if (!active) return;
        setTemplates([]);
      })
      .finally(() => {
        if (!active) return;
        setTemplatesLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setPromptTemplatesLoading(true);
    getJson<PromptTemplateListResponse>('/pipeline/prompts')
      .then((data) => {
        if (!active) return;
        const templateList = Array.isArray(data?.templates) ? data.templates : [];
        const assignmentList = Array.isArray(data?.assignments) ? data.assignments : [];
        const normalizedTemplates = templateList.map((template) => ({
          ...template,
          agent: normalizeAgentValue(template?.agent) ?? null,
          content: normalizePromptContent(template?.content),
        }));
        const normalizedAssignments = assignmentList.map((assignment) => ({
          ...assignment,
          agent: normalizeAgentValue(assignment?.agent) ?? null,
        }));
        setPromptTemplates(normalizedTemplates);
        setPromptAssignments(normalizedAssignments);
      })
      .catch(() => {
        if (!active) return;
        setPromptTemplates([]);
        setPromptAssignments([]);
      })
      .finally(() => {
        if (!active) return;
        setPromptTemplatesLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedPurposeId && purposes.length > 0) {
      setSelectedPurpose(purposes[0].id);
    }
  }, [purposes, selectedPurposeId, setSelectedPurpose]);

  useEffect(() => {
    if (!selectedPurposeId) return;
    const controller = new AbortController();
    const signal = controller.signal;
    fetchArtifacts(signal);
    fetchBacklog(signal);
    fetchGraphAndStatus(selectedPurposeId, signal);
    return () => controller.abort();
  }, [selectedPurposeId, fetchArtifacts, fetchBacklog, fetchGraphAndStatus]);

  useEffect(() => {
    if (!selectedPurposeId) {
      setCurrentTemplate(null);
      return;
    }
    let active = true;
    setLoadingPipeline(true);
    getJson<{ template: PipelineTemplateSummary }>(
      `/purposes/${selectedPurposeId}/pipeline`,
    )
      .then((data) => {
        if (!active) return;
        setCurrentTemplate(data?.template ?? null);
      })
      .catch(() => {
        if (!active) return;
        setCurrentTemplate(null);
      })
      .finally(() => {
        if (!active) return;
        setLoadingPipeline(false);
      });
    return () => {
      active = false;
    };
  }, [selectedPurposeId]);

  const toggleResearch = useCallback(async () => {
    if (allowResearch == null || updatingResearch) return;
    setUpdatingResearch(true);
    try {
      const res = await postJson<{ allow_web_research: boolean }>('/settings/research', {
        allow_web_research: !allowResearch,
      });
      const next = Boolean(res?.allow_web_research);
      setAllowResearch(next);
      toast.success(next ? 'Webrecherche aktiviert.' : 'Webrecherche deaktiviert.');
    } catch {
      toast.error('Webrecherche konnte nicht umgestellt werden.');
    } finally {
      setUpdatingResearch(false);
    }
  }, [allowResearch, updatingResearch]);

  const approveArtifact = useCallback(
    async (artifactId: string) => {
      const toastId = toast.loading('Artefakt wird freigegeben …');
      try {
        if (!selectedPurposeId) {
          throw new Error('purpose_missing');
        }
        await postJson(`/chat/messages`, {
          purpose_id: selectedPurposeId,
          artifact_ids: [artifactId],
          intent: 'approval',
          message: 'Approved',
        });
        if (selectedPurposeId) {
          await fetchGraphAndStatus(selectedPurposeId);
        }
        await fetchArtifacts();
        await fetchBacklog();
        toast.success('Artefakt freigegeben', { id: toastId });
      } catch {
        toast.error('Freigabe fehlgeschlagen', { id: toastId });
      }
    },
    [fetchArtifacts, fetchBacklog, fetchGraphAndStatus, selectedPurposeId],
  );

  const handleCreatePurpose = useCallback(
    async (purposeName: string, templateId?: string) => {
      const trimmed = purposeName.trim();
      if (!trimmed) return false;
      setCreatingPurpose(true);
      const toastId = toast.loading('Projektziel wird angelegt …');
      try {
        const payload: Record<string, unknown> = { purpose: trimmed };
        if (templateId) {
          payload.pipeline_template_id = templateId;
        }
        const res = await postJson<{ purpose_id: string }>('/purposes', payload);
        const newPurposeId = res?.purpose_id;
        if (newPurposeId) {
          setSelectedPurpose(newPurposeId);
        }
        await fetchPurposes();
        if (newPurposeId) {
          await fetchGraphAndStatus(newPurposeId);
        }
        await fetchArtifacts();
        await fetchBacklog();
        if (!templatesLoading) {
          getJson<PipelineTemplateSummary[]>('/pipeline/templates')
            .then((data) => {
              const list = Array.isArray(data) ? data : [];
              setTemplates(list);
            })
            .catch(() => setTemplates([]));
        }
        toast.success('Projektziel erstellt.', { id: toastId });
        return true;
      } catch {
        toast.error('Projektziel konnte nicht erstellt werden.', { id: toastId });
        return false;
      } finally {
        setCreatingPurpose(false);
      }
    },
    [
      fetchArtifacts,
      fetchBacklog,
      fetchGraphAndStatus,
      fetchPurposes,
      setSelectedPurpose,
      templatesLoading,
    ],
  );

  const visionArtifacts = artifacts.filter((a) =>
    a.repo_path?.toLowerCase().includes('vision/'),
  );
  const visionArtifact =
    visionArtifacts.length > 0 ? visionArtifacts[visionArtifacts.length - 1] : undefined;

  const prdArtifacts = artifacts.filter((a) =>
    a.repo_path?.toLowerCase().includes('product_requirements'),
  );
  const prdArtifact = prdArtifacts.length > 0 ? prdArtifacts[prdArtifacts.length - 1] : undefined;
  const visionAwaitingApproval = !!visionArtifact && !visionArtifact.released;
  const archArtifact = artifacts.find((a) =>
    a.repo_path?.toLowerCase().includes('architecture_blueprint'),
  );
  const architectureReviewArtifact = artifacts.find((a) =>
    a.repo_path?.toLowerCase().includes('architecture_domain_review'),
  );
  const architectureArtifactId = archArtifact?.id ?? null;
  const architectureReviewArtifactId = architectureReviewArtifact?.id ?? null;

  const prdAwaitingApproval = !!prdArtifact && !prdArtifact.released;
  const architectureAwaitingApproval = !!archArtifact && !archArtifact.released;
  const architectureReviewAwaitingApproval =
    !!architectureReviewArtifact && !architectureReviewArtifact.released;

  const buildStatusIcon = (
    state: 'missing' | 'pending' | 'done',
    label: string,
  ): ReactNode => {
    const { Icon, classes } =
      state === 'done'
        ? { Icon: CheckCircle2, classes: 'border-green-200 bg-green-50 text-green-600 dark:border-green-500/60 dark:bg-green-500/10 dark:text-green-300' }
        : state === 'pending'
          ? { Icon: Clock3, classes: 'border-amber-200 bg-amber-50 text-amber-600 dark:border-amber-400/60 dark:bg-amber-500/10 dark:text-amber-200' }
          : { Icon: CircleDashed, classes: 'border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-600 dark:bg-slate-800/60 dark:text-slate-300' };
    return (
      <span
        className={`inline-flex h-7 w-7 items-center justify-center rounded-full border ${classes}`}
        role="img"
        aria-label={label}
        title={label}
      >
        <Icon className="h-4 w-4" aria-hidden />
      </span>
    );
  };

  const visionStatusIcon = buildStatusIcon(
    visionArtifact ? (visionAwaitingApproval ? 'pending' : 'done') : 'missing',
    visionArtifact
      ? visionAwaitingApproval
        ? 'Vision wartet auf Freigabe'
        : 'Vision freigegeben'
      : 'Vision wird erstellt',
  );
  const prdStatusIcon = buildStatusIcon(
    prdArtifact ? (prdAwaitingApproval ? 'pending' : 'done') : 'missing',
    prdArtifact
      ? prdAwaitingApproval
        ? 'Produktanforderung wartet auf Freigabe'
        : 'Produktanforderung freigegeben'
      : 'Produktanforderung wird erstellt',
  );
  const archStatusIcon = buildStatusIcon(
    archArtifact ? (architectureAwaitingApproval ? 'pending' : 'done') : 'missing',
    archArtifact
      ? architectureAwaitingApproval
        ? 'Architektur wartet auf Feedback'
        : 'Architektur bestätigt'
      : 'Architektur in Vorbereitung',
  );
  const architectureReviewStatusIcon = buildStatusIcon(
    architectureReviewArtifact
      ? architectureReviewAwaitingApproval
        ? 'pending'
        : 'done'
      : 'missing',
    architectureReviewArtifact
      ? architectureReviewAwaitingApproval
        ? 'Review wartet auf Freigabe'
        : 'Review abgeschlossen'
      : 'Review in Erstellung',
  );
  const graphStatusIcon = buildStatusIcon(
    paused ? 'pending' : graphNodes.length > 0 ? 'done' : 'missing',
    paused ? 'Pipeline pausiert' : 'Task-Graph bereit',
  );

  const tasksStatusValues = Object.values(tasksStatus ?? {});
  const hasTasks = tasksStatusValues.length > 0;
  const allTasksDone = hasTasks && tasksStatusValues.every((status) => status === 'done');
  const backlogEmpty = backlog.length === 0;
  const releasedArtifacts = artifacts.filter((a) => a.released);
  const allArtifactsReleased = artifacts.length > 0 && releasedArtifacts.length === artifacts.length;
  const selectedPurpose = purposes.find((p) => p.id === selectedPurposeId) || null;
  const budgetLabel =
    budgetLeft != null && budgetTotal != null
      ? `${budgetLeft.toFixed(2)} / ${budgetTotal.toFixed(2)} USD`
      : '…';

  const statusInfo: Record<string, { label: string; color: string }> = {
    todo: { label: 'Todo', color: 'bg-yellow-500 text-black' },
    doing: { label: 'In Progress', color: 'bg-blue-500 text-white' },
    done: { label: 'Done', color: 'bg-green-600 text-white' },
    failed: { label: 'Failed', color: 'bg-red-600 text-white' },
    blocked: { label: 'Blocked', color: 'bg-gray-500 text-white' },
    skipped: { label: 'Skipped', color: 'bg-gray-500 text-white' },
    budget_exceeded: {
      label: 'Blocked (Budget)',
      color: 'bg-gray-500 text-white',
    },
  };

  const statusCounters = useMemo(
    () =>
      tasksStatusValues.reduce<Record<string, number>>((acc, status) => {
        acc[status] = (acc[status] ?? 0) + 1;
        return acc;
      }, {}),
    [tasksStatusValues],
  );

  const purposeCompleted = Boolean(selectedPurposeId);
  const visionCompleted = Boolean(visionArtifact?.released);
  const prdCompleted = Boolean(prdArtifact?.released);
  const architectureCompleted = Boolean(archArtifact?.released);
  const architectureReviewCompleted = Boolean(architectureReviewArtifact?.released);
  const implementationCompleted = allTasksDone;
  const reviewCompleted = implementationCompleted && backlogEmpty;
  const releaseCompleted = reviewCompleted && allArtifactsReleased;

  const phaseCompletion: Record<PhaseId, boolean> = {
    purpose: purposeCompleted,
    vision: visionCompleted,
    prd: prdCompleted,
    architecture: architectureCompleted,
    architecture_review: architectureReviewCompleted,
    implementation: implementationCompleted,
    review: reviewCompleted,
    release: releaseCompleted,
  };

  const recommendedPhase = useMemo<PhaseId>(() => {
    if (!purposeCompleted) return 'purpose';
    if (!visionArtifact || !visionArtifact.released) return 'vision';
    if (!prdArtifact || !prdArtifact.released) return 'prd';
    if (!archArtifact || !archArtifact.released) return 'architecture';
    if (!architectureReviewArtifact || !architectureReviewArtifact.released)
      return 'architecture_review';
    if (!implementationCompleted) return 'implementation';
    if (!reviewCompleted) return 'review';
    if (!releaseCompleted) return 'release';
    return 'release';
  }, [
    purposeCompleted,
    visionArtifact,
    prdArtifact,
    archArtifact,
    architectureReviewArtifact,
    implementationCompleted,
    reviewCompleted,
    releaseCompleted,
  ]);

  const [currentPhase, setCurrentPhaseInternal] = useState<PhaseId>(recommendedPhase);
  const userSelectedPhaseRef = useRef(false);

  useEffect(() => {
    setCurrentPhaseInternal((prev) => {
      const prevIndex = PHASE_ORDER.indexOf(prev);
      const recommendedIndex = PHASE_ORDER.indexOf(recommendedPhase);
      if (!userSelectedPhaseRef.current || recommendedIndex > prevIndex) {
        userSelectedPhaseRef.current = false;
        return recommendedPhase;
      }
      return prev;
    });
  }, [recommendedPhase]);

  const setPhase = useCallback((phase: PhaseId) => {
    userSelectedPhaseRef.current = true;
    setCurrentPhaseInternal(phase);
  }, []);

  useEffect(() => {
    if (!autoPipeline) {
      return;
    }
    if (currentPhase === 'vision' && visionArtifact && !visionArtifact.released) {
      void approveArtifact(visionArtifact.id);
    } else if (currentPhase === 'prd' && prdArtifact && !prdArtifact.released) {
      void approveArtifact(prdArtifact.id);
    } else if (currentPhase === 'architecture' && archArtifact && !archArtifact.released) {
      void approveArtifact(archArtifact.id);
    } else if (
      currentPhase === 'architecture_review' &&
      architectureReviewArtifact &&
      !architectureReviewArtifact.released
    ) {
      void approveArtifact(architectureReviewArtifact.id);
    }
  }, [
    approveArtifact,
    archArtifact,
    architectureReviewArtifact,
    autoPipeline,
    currentPhase,
    prdArtifact,
    visionArtifact,
  ]);

  const handlePhaseSelect = (phase: PhaseId) => {
    setPhase(phase);
  };

  const getNextPhase = (phase: PhaseId): PhaseId | null => {
    const index = PHASE_ORDER.indexOf(phase);
    if (index === -1 || index >= PHASE_ORDER.length - 1) {
      return null;
    }
    return PHASE_ORDER[index + 1];
  };

  const handleArtifactApproved = (phase: PhaseId) => {
    const nextPhase = getNextPhase(phase);
    if (!nextPhase) return;
    setPhase(nextPhase);
    const refreshPromises: Promise<unknown>[] = [fetchArtifacts(), fetchBacklog()];
    if (selectedPurposeId) {
      refreshPromises.push(fetchGraphAndStatus(selectedPurposeId));
    }
    void Promise.all(refreshPromises);
  };

  const phases = useMemo<PhaseMeta[]>(() => {
    let previousCompleted = true;
    return PIPELINE_PHASES.map((phase, index) => {
      const completed = phaseCompletion[phase.id];
      const isCurrent = currentPhase === phase.id;
      const isUpcoming = !completed && !previousCompleted && !isCurrent;
      if (!completed) {
        previousCompleted = false;
      }
      return {
        id: phase.id,
        title: phase.title,
        icon: phase.icon,
        completed,
        index,
        isCurrent,
        isUpcoming,
      } satisfies PhaseMeta;
    });
  }, [
    currentPhase,
    purposeCompleted,
    visionCompleted,
    prdCompleted,
    architectureCompleted,
    architectureReviewCompleted,
    implementationCompleted,
    reviewCompleted,
    releaseCompleted,
  ]);

  const currentPhaseMeta = phases.find((phase) => phase.id === currentPhase) ?? phases[0];

  const currentPhaseSlug = currentPhase ? PHASE_TO_TEMPLATE_SLUG[currentPhase] ?? null : null;
  const currentPhaseDefaults = useMemo<PipelinePhaseDefaults | null>(() => {
    if (!currentTemplate || !currentPhaseSlug) return null;
    return (
      currentTemplate.phases.find((phase) => phase.slug === currentPhaseSlug) ?? null
    );
  }, [currentTemplate, currentPhaseSlug]);

  const tenantDefaultTemplate = useMemo<PromptTemplateRecord | null>(() => {
    if (!currentPhaseDefaults) return null;
    const slug = currentPhaseDefaults.slug;
    return (
      promptTemplates.find(
        (template) => template.phase_slug === slug && template.is_tenant_default,
      ) ?? null
    );
  }, [promptTemplates, currentPhaseDefaults]);

  const currentPromptRecord = useMemo<PromptTemplateRecord | null>(() => {
    if (!currentPhaseDefaults) return null;
    const key = currentPhaseDefaults.prompt_template;
    if (!key) return null;
    return (
      promptTemplates.find((template) => template.id === key) ??
      promptTemplates.find(
        (template) => template.default_path === key && !template.tenant_id,
      ) ??
      null
    );
  }, [promptTemplates, currentPhaseDefaults]);

  const effectivePromptRecord = useMemo<PromptTemplateRecord | null>(() => {
    if (currentPromptRecord && currentPromptRecord.tenant_id) {
      return currentPromptRecord;
    }
    if (tenantDefaultTemplate) {
      return tenantDefaultTemplate;
    }
    return currentPromptRecord;
  }, [currentPromptRecord, tenantDefaultTemplate]);

  const basePromptContent = useMemo<string>(() => {
    if (
      effectivePromptRecord &&
      effectivePromptRecord.content !== undefined &&
      effectivePromptRecord.content !== null
    ) {
      return normalizePromptContent(effectivePromptRecord.content);
    }
    return normalizePromptContent(currentPhaseDefaults?.prompt_template);
  }, [effectivePromptRecord, currentPhaseDefaults]);

  const handlePhaseSettingsSave = useCallback(async () => {
    if (!selectedPurposeId || !currentPhaseDefaults) return;
    const baseTokens = currentPhaseDefaults.tokens_plan_default ?? 0;
    const parsedTokens = phaseTokens.trim() === '' ? baseTokens : Number(phaseTokens);
    const tokensValue = Number.isFinite(parsedTokens)
      ? Math.max(0, Math.trunc(parsedTokens))
      : baseTokens;

    const payload: Record<string, unknown> = {
      purpose_id: selectedPurposeId,
      scope: phaseScope,
      tokens_plan_default: tokensValue,
      model_name: phaseModel || null,
    };

    setPhaseSaving(true);
    const toastId = toast.loading('Phase wird aktualisiert …');
    let successMessage = 'Phase aktualisiert.';

    try {
      let promptTemplateId: string | null | undefined =
        currentPhaseDefaults.prompt_template ?? null;

      if (phaseScope === 'tenant_default') {
        if (!phasePrompt.trim()) {
          throw new Error('Prompt darf nicht leer sein.');
        }

        if (tenantDefaultTemplate && tenantDefaultTemplate.tenant_id) {
          if (
            (phasePrompt || '').trim() !==
            (tenantDefaultTemplate.content || '').trim()
          ) {
            await putJson(`/pipeline/prompts/update/${tenantDefaultTemplate.id}`, {
              content: phasePrompt,
            });
          }
          promptTemplateId = tenantDefaultTemplate.id;
          successMessage = 'Mandanten-Prompt aktualisiert.';
        } else if (
          (phasePrompt || '').trim() !== (basePromptContent || '').trim()
        ) {
          const created = await postJson<{ id: string }>(
            '/pipeline/prompts/create',
            {
              phase_slug: currentPhaseDefaults.slug,
              content: phasePrompt,
              agent: currentPhaseDefaults.agent_role ?? null,
              set_default: true,
              purpose_id: selectedPurposeId,
            },
          );
          promptTemplateId = created?.id ?? null;
          successMessage = 'Prompt-Vorlage als Mandanten-Standard gespeichert.';
        } else {
          promptTemplateId = currentPromptRecord?.id ?? promptTemplateId ?? null;
        }
      } else if (phaseScope === 'template') {
        const globalTemplate =
          (currentPromptRecord && !currentPromptRecord.tenant_id
            ? currentPromptRecord
            : null) ??
          promptTemplates.find(
            (template) =>
              template.phase_slug === currentPhaseDefaults.slug && !template.tenant_id,
          );
        if (!globalTemplate) {
          throw new Error('Globales Template nicht gefunden.');
        }
        if ((phasePrompt || '').trim() !== (basePromptContent || '').trim()) {
          await putJson(`/pipeline/prompts/update/${globalTemplate.id}`, {
            content: phasePrompt,
          });
        }
        promptTemplateId = globalTemplate.id;
        successMessage = 'Globale Prompt-Vorlage aktualisiert.';
      } else {
        if (!(phasePrompt || '').trim()) {
          promptTemplateId = null;
        } else if ((phasePrompt || '').trim() !== (basePromptContent || '').trim()) {
          if (
            currentPromptRecord &&
            currentPromptRecord.tenant_id &&
            !currentPromptRecord.is_tenant_default
          ) {
            await putJson(`/pipeline/prompts/update/${currentPromptRecord.id}`, {
              content: phasePrompt,
            });
            promptTemplateId = currentPromptRecord.id;
          } else {
            const created = await postJson<{ id: string }>(
              '/pipeline/prompts/create',
              {
                phase_slug: currentPhaseDefaults.slug,
                content: phasePrompt,
                agent: currentPhaseDefaults.agent_role ?? null,
              },
            );
            promptTemplateId = created?.id ?? null;
          }
        } else if (currentPromptRecord) {
          promptTemplateId = currentPromptRecord.id;
        }
      }

      if (promptTemplateId !== undefined) {
        payload.prompt_template = promptTemplateId;
      }

      const response = await putJson<{ template: PipelineTemplateSummary }>(
        `/pipeline/phases/${currentPhaseDefaults.id}`,
        payload,
      );
      if (response?.template) {
        setCurrentTemplate(response.template);
      }

      await fetchGraphAndStatus(selectedPurposeId);
      await fetchBacklog();

      const [templateList, promptList] = await Promise.all([
        getJson<PipelineTemplateSummary[]>('/pipeline/templates'),
        getJson<PromptTemplateListResponse>('/pipeline/prompts'),
      ]);
      setTemplates(Array.isArray(templateList) ? templateList : []);
      setPromptTemplates(Array.isArray(promptList?.templates) ? promptList.templates : []);
      setPromptAssignments(
        Array.isArray(promptList?.assignments) ? promptList.assignments : [],
      );

      toast.success(successMessage, { id: toastId });
    } catch (error) {
      console.error(error);
      toast.error('Einstellungen konnten nicht gespeichert werden.', { id: toastId });
    } finally {
      setPhaseSaving(false);
    }
  }, [
    basePromptContent,
    currentPhaseDefaults,
    currentPromptRecord,
    fetchBacklog,
    fetchGraphAndStatus,
    phaseModel,
    phasePrompt,
    phaseScope,
    phaseTokens,
    promptTemplates,
    selectedPurposeId,
    tenantDefaultTemplate,
  ]);

  const isTenantDefaultActive = Boolean(
    tenantDefaultTemplate && tenantDefaultTemplate.tenant_id,
  );
  const isPurposeSpecificPrompt = Boolean(
    currentPromptRecord?.tenant_id && !currentPromptRecord?.is_tenant_default,
  );
  const editorTheme =
    typeof document !== 'undefined' &&
    document.documentElement.classList.contains('dark')
      ? 'vs-dark'
      : 'vs-light';

  useEffect(() => {
    if (!currentPhaseDefaults) {
      setPhaseModel('');
      setPhaseTokens('');
      setPhasePrompt('');
      return;
    }
    setPhaseModel(currentPhaseDefaults.model_name ?? '');
    setPhaseTokens(
      currentPhaseDefaults.tokens_plan_default != null
        ? String(currentPhaseDefaults.tokens_plan_default)
        : '',
    );
    setPhasePrompt(basePromptContent ?? '');
    setPhaseScope('purpose');
    setPromptExpanded(false);
  }, [currentPhaseDefaults, basePromptContent]);

  const baseTokens = currentPhaseDefaults?.tokens_plan_default ?? 0;
  const parsedTokens = phaseTokens.trim() === '' ? baseTokens : Number(phaseTokens);
  const normalizedTokens = Number.isFinite(parsedTokens)
    ? Math.max(0, Math.trunc(parsedTokens))
    : baseTokens;
  const hasPhaseChanges = Boolean(
    currentPhaseDefaults &&
      ((phaseModel || '') !== (currentPhaseDefaults.model_name ?? '') ||
        normalizedTokens !== baseTokens ||
        (phasePrompt || '').trim() !== (basePromptContent || '').trim()),
  );
  const canSavePhase = Boolean(
    currentPhaseDefaults &&
      !phaseSaving &&
      (hasPhaseChanges || phaseScope !== 'purpose'),
  );

  const getPhaseStatusLabel = (phase: PhaseMeta) => {
    if (phase.completed) return 'Abgeschlossen';
    if (phase.isCurrent) return 'Aktive Phase';
    if (phase.isUpcoming) return 'Geplant';
    return 'Bereit';
  };

  const phaseNavItems = useMemo<PhaseNavItem[]>(
    () =>
      phases.map((phase) => ({
        ...phase,
        statusLabel: getPhaseStatusLabel(phase),
      })),
    [phases],
  );

  const renderBacklogSection = () => (
    <section className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-700 dark:text-slate-200">
          <History className="h-4 w-4 text-slate-500 dark:text-slate-400" /> Aufgaben-Backlog
        </h3>
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
          {backlog.length > 0 ? `${backlog.length} offene Einträge` : 'keine offenen Aufgaben'}
        </span>
      </div>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        {backlog.length > 0
          ? 'Überwache den Status der Aufgaben und gib bei Bedarf Rückmeldung, um Blocker schnell zu erkennen.'
          : 'Der Backlog ist aktuell leer – sobald neue Aufgaben geplant werden, erscheinen sie hier.'}
      </p>
      <ul className="mt-4 space-y-2 text-sm">
        {backlog.map((t: any) => (
          <li
            key={t.id}
            className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <div className="text-slate-700 dark:text-slate-200">
              <span className="text-amber-500 font-mono mr-2">{t.id}</span>
              {t.description}
            </div>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
                statusInfo[t.status]?.color ?? 'bg-slate-200 text-slate-700'
              }`}
            >
              {statusInfo[t.status]?.label ?? t.status}
            </span>
          </li>
        ))}
        {backlog.length === 0 && (
          <li className="italic text-slate-500 dark:text-slate-400">Keine offenen Aufgaben 🎉</li>
        )}
      </ul>
    </section>
  );

  const phaseContext: PhaseViewContext = {
    purposes,
    selectedPurpose,
    selectedPurposeId,
    paused,
    onCreatePurpose: handleCreatePurpose,
    creatingPurpose,
    templates,
    defaultTemplateId,
    visionArtifact,
    visionAwaitingApproval,
    visionStatusIcon,
    onVisionApproved: () => handleArtifactApproved('vision'),
    prdArtifact,
    prdAwaitingApproval,
    prdStatusIcon,
    onPrdApproved: () => handleArtifactApproved('prd'),
    archArtifact,
    architectureAwaitingApproval,
    archStatusIcon,
    onArchitectureApproved: () => handleArtifactApproved('architecture'),
    architectureReviewArtifact,
    architectureReviewAwaitingApproval,
    architectureReviewStatusIcon,
    onArchitectureReviewApproved: () =>
      handleArtifactApproved('architecture_review'),
    graphNodes,
    graphEdges,
    graphStatusIcon,
    renderBacklogSection,
    artifacts,
    releasedArtifacts,
    hasTasks,
    statusInfo,
    statusCounters,
    allTasksDone,
    backlogEmpty,
    implementationCompleted,
    allArtifactsReleased,
    releaseCompleted,
  };

  const PhaseContentComponent = PHASE_CONTENT_COMPONENTS[currentPhase];
  const PhaseSidebarComponent = PHASE_SIDEBAR_COMPONENTS[currentPhase];

  const phaseContent = (
    <Suspense fallback={<div>Lade Phase-Inhalt…</div>}>
      <PhaseContentComponent {...phaseContext} />
    </Suspense>
  );

  const phaseSidebarContent = (
    <Suspense fallback={null}>
      <PhaseSidebarComponent {...phaseContext} />
    </Suspense>
  );

  function downloadArtifactFile(artifactId: string, filename: string) {
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
  }

  return (
    <div className="flex flex-col h-screen">
      <div className="bg-gray-100 dark:bg-slate-800 p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-4">
            <PurposeSelector />
            <button
              type="button"
              onClick={toggleResearch}
              disabled={allowResearch == null || updatingResearch}
              className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition ${
                allowResearch
                  ? 'bg-emerald-600 hover:bg-emerald-700 text-white dark:bg-emerald-600 dark:hover:bg-emerald-700'
                  : 'bg-slate-200 hover:bg-slate-300 text-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600 dark:text-slate-100'
              } disabled:cursor-not-allowed disabled:opacity-60`}
            >
              {(allowResearch ?? false) ? (
                <PauseCircle className="h-4 w-4" aria-hidden />
              ) : (
                <PlayCircle className="h-4 w-4" aria-hidden />
              )}
              {allowResearch == null ? 'Web …' : allowResearch ? 'Web aus' : 'Web an'}
            </button>
            <button
              type="button"
              onClick={toggleAutoPipeline}
              className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition ${
                autoPipeline
                  ? 'bg-purple-600 hover:bg-purple-700 text-white dark:bg-purple-600 dark:hover:bg-purple-700'
                  : 'bg-slate-200 hover:bg-slate-300 text-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600 dark:text-slate-100'
              }`}
            >
              {autoPipeline ? (
                <PauseCircle className="h-4 w-4" aria-hidden />
              ) : (
                <PlayCircle className="h-4 w-4" aria-hidden />
              )}
              {autoPipeline ? 'Auto aus' : 'Auto an'}
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Status
              </span>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${
                  paused
                    ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300'
                    : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300'
                }`}
              >
                {paused ? (
                  <>
                    <Clock3 className="h-4 w-4" aria-hidden /> Pausiert
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-4 w-4" aria-hidden /> Läuft
                  </>
                )}
              </span>
            </div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Budget:{' '}
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">{budgetLabel}</span>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-50 dark:bg-red-900 text-red-600 dark:text-red-500 border-b">
          {typeof error === 'string'
            ? error
            : error instanceof Error
              ? error.message
              : String(error)}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <nav className="w-64 flex-shrink-0 border-r border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 overflow-y-auto">
          <div className="mb-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Phasen</h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Navigiere zwischen den Arbeitsschritten der Pipeline.
            </p>
          </div>
          <PhaseNavigation items={phaseNavItems} onSelect={handlePhaseSelect} />
        </nav>

        <div className="main-panel flex-1 overflow-y-auto p-6 bg-white dark:bg-slate-900/40">
          <div className="space-y-6">
            {currentPhaseMeta && (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
                    {currentPhaseMeta.title}
                  </h1>
                  <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                    {PHASE_DESCRIPTIONS[currentPhaseMeta.id]}
                  </p>
                </div>
                {currentPhaseMeta.completed && (
                  <span className="inline-flex items-center gap-1 self-start rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700 dark:bg-green-500/10 dark:text-green-300">
                    <CheckCircle2 className="h-4 w-4" /> Abgeschlossen
                  </span>
                )}
              </div>
            )}
            {isLoading && <p className="text-sm text-slate-500">Lade...</p>}
            {phaseContent}
            {!autoPipeline && currentPhase === 'vision' && visionArtifact && !visionArtifact.released && (
              <button
                onClick={() => void approveArtifact(visionArtifact.id)}
                className="mt-4 inline-flex items-center justify-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700"
              >
                Vision freigeben
              </button>
            )}
            {!autoPipeline && currentPhase === 'prd' && prdArtifact && !prdArtifact.released && (
              <button
                onClick={() => void approveArtifact(prdArtifact.id)}
                className="mt-4 inline-flex items-center justify-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700"
              >
                PRD freigeben
              </button>
            )}
            {!autoPipeline && currentPhase === 'architecture' && archArtifact && !archArtifact.released && (
              <button
                onClick={() => void approveArtifact(archArtifact.id)}
                className="mt-4 inline-flex items-center justify-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700"
              >
                Architektur freigeben
              </button>
            )}
            {!autoPipeline &&
              currentPhase === 'architecture_review' &&
              architectureReviewArtifact &&
              !architectureReviewArtifact.released && (
                <button
                  onClick={() => void approveArtifact(architectureReviewArtifact.id)}
                  className="mt-4 inline-flex items-center justify-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700"
                >
                  Review freigeben
                </button>
              )}
          </div>
        </div>

        <aside className="w-80 flex-shrink-0 border-l border-slate-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800 p-4 overflow-y-auto">
          <section className="mb-6 rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                Phase-Einstellungen
              </h2>
              {currentTemplate && (
                <span className="text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
                  {currentTemplate.name}
                </span>
              )}
            </div>
            {!selectedPurposeId ? (
              <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                Wähle ein Projektziel aus, um Einstellungen anzupassen.
              </p>
            ) : loadingPipeline ? (
              <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Lade Phase …</p>
            ) : !currentPhaseDefaults ? (
              <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                Für diese Phase stehen derzeit keine konfigurierbaren Einstellungen zur Verfügung.
              </p>
            ) : (
              <form className="mt-3 space-y-3" onSubmit={(event) => event.preventDefault()}>
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500" htmlFor="phase-model-select">
                    Modell
                  </label>
                  <select
                    id="phase-model-select"
                    className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm transition focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                    value={phaseModel}
                    onChange={(event) => setPhaseModel(event.target.value)}
                    disabled={phaseSaving}
                  >
                    {MODEL_OPTIONS.map((option) => (
                      <option key={option.value || 'default'} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500" htmlFor="phase-token-input">
                    Token-Limit
                  </label>
                  <input
                    id="phase-token-input"
                    type="number"
                    min={0}
                    step={100}
                    className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm transition focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                    value={phaseTokens}
                    onChange={(event) => setPhaseTokens(event.target.value)}
                    disabled={phaseSaving}
                  />
                </div>
                <div className="space-y-2">
                  <button
                    type="button"
                    onClick={() => setPromptExpanded((prev) => !prev)}
                    className="text-xs font-semibold text-amber-600 hover:text-amber-500"
                  >
                    {promptExpanded ? 'Prompt verbergen' : 'Prompt anzeigen & bearbeiten'}
                  </button>
                  {promptExpanded && (
                    <div className="space-y-1">
                      {promptTemplatesLoading ? (
                        <p className="text-xs text-slate-600 dark:text-slate-400">
                          Prompt-Vorlagen werden geladen …
                        </p>
                      ) : isTenantDefaultActive ? (
                        <p className="text-xs text-blue-600 dark:text-blue-300">
                          Hinweis: Für diese Phase ist ein mandantenspezifisches Prompt aktiv.
                        </p>
                      ) : isPurposeSpecificPrompt ? (
                        <p className="text-xs text-emerald-600 dark:text-emerald-300">
                          Hinweis: Dieses Projekt verwendet ein eigenes Prompt-Template.
                        </p>
                      ) : (
                        <p className="text-xs text-slate-600 dark:text-slate-400">
                          Verwendung des globalen Standard-Templates.
                        </p>
                      )}
                      <div className="overflow-hidden rounded-md border border-slate-300 dark:border-slate-600">
                        <Editor
                          height="200px"
                          defaultLanguage="jinja"
                          value={phasePrompt}
                          onChange={(value) => setPhasePrompt(value ?? '')}
                          theme={editorTheme}
                          options={{
                            minimap: { enabled: false },
                            fontSize: 12,
                            readOnly: phaseSaving,
                            wordWrap: 'on',
                          }}
                        />
                      </div>
                    </div>
                  )}
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500" htmlFor="phase-scope-select">
                    Änderungen anwenden auf
                  </label>
                  <select
                    id="phase-scope-select"
                    className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm transition focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                    value={phaseScope}
                    onChange={(event) => setPhaseScope(event.target.value as typeof phaseScope)}
                    disabled={phaseSaving}
                  >
                    {SCOPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  onClick={handlePhaseSettingsSave}
                  disabled={!canSavePhase}
                  className="w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-400 disabled:text-slate-200"
                >
                  {phaseSaving ? 'Speichere …' : 'Einstellungen speichern'}
                </button>
              </form>
            )}
          </section>

          {phaseSidebarContent && <div className="mb-6">{phaseSidebarContent}</div>}

          <h2 className="flex items-center gap-2 text-lg mb-2 text-slate-700 dark:text-slate-200">
            <Package className="w-4 h-4" /> Artifacts
          </h2>
          <ul className="space-y-2 text-sm">
            {artifacts.map((a) => (
              <li
                key={a.id}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-900"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-amber-500 font-mono text-xs">{a.task_id}</span>
                  {a.released && (
                    <span className="text-xs font-semibold text-green-600 dark:text-green-400">released</span>
                  )}
                </div>
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    downloadArtifactFile(a.id, a.repo_path?.split('/').pop() || a.id);
                  }}
                  className="mt-1 block truncate text-amber-500 hover:underline"
                >
                  {a.repo_path?.replace(/^[^/]+\//, '')}
                </a>
                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {a.media_type}, {a.created_at ? new Date(a.created_at).toLocaleString() : 'unbekannt'}
                </div>
              </li>
            ))}
            {artifacts.length === 0 && (
              <li className="italic text-slate-500 dark:text-slate-400">No artifacts yet</li>
            )}
          </ul>
        </aside>
      </div>
    </div>
  );
}
