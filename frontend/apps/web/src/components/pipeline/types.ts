import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import type { PhaseId } from './phaseConfig';

export interface ArtifactItem {
  id: string;
  repo_path?: string;
  url?: string;
  created_at?: string;
  media_type?: string;
  released?: boolean;
  task_id?: string;
  task_desc?: string;
}

export interface PipelinePhaseDefaults {
  id: string;
  slug: string;
  name: string;
  position: number;
  predecessor_id?: string | null;
  agent_role?: string | null;
  prompt_template?: string | null;
  model_name?: string | null;
  tokens_plan_default?: number;
  business_value_default?: number;
  purpose_relevance_default?: number;
  requires_approval?: boolean;
}

export interface PipelineTemplateSummary {
  id: string;
  name: string;
  description?: string | null;
  tenant_id?: string | null;
  is_default?: boolean;
  phases: PipelinePhaseDefaults[];
}

export interface PromptTemplateRecord {
  id: string;
  phase_slug: string;
  /** optionale Metadaten für feinere Auswahl */
  agent?: string | null;
  name?: string | null;
  default_path?: string | null;
  content: string;
  tenant_id?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  is_tenant_default?: boolean;
  assignment_id?: string | null;
}

export interface PromptAssignmentSummary {
  id: string;
  phase_slug: string;
  prompt_template_id: string;
  /** wenn Backend dies liefert: */
  agent?: string | null;
  purpose_id?: string | null;
  created_at?: string | null;
}

export interface PromptTemplateListResponse {
  templates: PromptTemplateRecord[];
  assignments: PromptAssignmentSummary[];
}

export interface PurposeSummary {
  id: string;
  name: string;
  mode?: 'manual' | 'auto';
}

export interface PipelineGraphNode {
  id: string;
  data: { label: string; status?: string };
  position: { x: number; y: number };
  style?: Record<string, string>;
}

export interface PipelineGraphEdge {
  id: string;
  source: string;
  target: string;
}

export type StatusInfoMap = Record<string, { label: string; color: string }>;

export interface PhaseNavItem {
  id: PhaseId;
  title: string;
  icon: LucideIcon;
  completed: boolean;
  index: number;
  isCurrent: boolean;
  isUpcoming: boolean;
  statusLabel: string;
}

export interface PhaseViewContext {
  purposes: PurposeSummary[];
  selectedPurpose: PurposeSummary | null;
  selectedPurposeId: string | null;
  paused: boolean;
  chatFilterValue: string;
  setChatFilterValue: (value: string) => void;
  onCreatePurpose?: (name: string, templateId?: string) => Promise<boolean>;
  creatingPurpose?: boolean;
  templates?: PipelineTemplateSummary[];
  defaultTemplateId?: string | null;
  visionArtifact?: ArtifactItem;
  visionAwaitingApproval: boolean;
  visionStatusIcon: ReactNode;
  onVisionApproved: (
    info?: { redirectArtifactId?: string; redirectArtifactUrl?: string },
  ) => void;
  prdArtifact?: ArtifactItem;
  prdAwaitingApproval: boolean;
  prdStatusIcon: ReactNode;
  onPrdApproved: (
    info?: { redirectArtifactId?: string; redirectArtifactUrl?: string },
  ) => void;
  archArtifact?: ArtifactItem;
  architectureAwaitingApproval: boolean;
  archStatusIcon: ReactNode;
  onArchitectureApproved: (
    info?: { redirectArtifactId?: string; redirectArtifactUrl?: string },
  ) => void;
  architectureReviewArtifact?: ArtifactItem;
  architectureReviewAwaitingApproval: boolean;
  architectureReviewStatusIcon: ReactNode;
  onArchitectureReviewApproved: (
    info?: { redirectArtifactId?: string; redirectArtifactUrl?: string },
  ) => void;
  graphNodes: PipelineGraphNode[];
  graphEdges: PipelineGraphEdge[];
  graphStatusIcon: ReactNode;
  renderBacklogSection: () => ReactNode;
  artifacts: ArtifactItem[];
  releasedArtifacts: ArtifactItem[];
  hasTasks: boolean;
  statusInfo: StatusInfoMap;
  statusCounters: Record<string, number>;
  allTasksDone: boolean;
  backlogEmpty: boolean;
  implementationCompleted: boolean;
  allArtifactsReleased: boolean;
  releaseCompleted: boolean;
}
