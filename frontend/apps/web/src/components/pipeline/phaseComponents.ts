import type { ComponentType } from 'react';
import type { PhaseId } from './phaseConfig';
import type { PhaseViewContext } from './types';

// Importiere alle Phasen-Komponenten direkt aus ihren Quelldateien
import {
  PurposePhaseContent,
  PurposePhaseSidebar,
} from './phases/PurposePhase';
import {
  VisionPhaseContent,
  VisionPhaseSidebar,
} from './phases/VisionPhase';
import { PrdPhaseContent, PrdPhaseSidebar } from './phases/PrdPhase';
import {
  ArchitecturePhaseContent,
  ArchitecturePhaseSidebar,
} from './phases/ArchitecturePhase';
import {
  ArchitectureReviewPhaseContent,
  ArchitectureReviewPhaseSidebar,
} from './phases/ArchitectureReviewPhase';
import {
  ImplementationPhaseContent,
  ImplementationPhaseSidebar,
} from './phases/ImplementationPhase';
import { ReviewPhaseContent, ReviewPhaseSidebar } from './phases/ReviewPhase';
import { ReleasePhaseContent, ReleasePhaseSidebar } from './phases/ReleasePhase';

/**
 * Zuordnung der Content-Komponenten zu den Phasen-IDs. Jede Phase wird
 * explizit ihrer Komponente zugewiesen, sodass es keine zirkulären Abhängigkeiten gibt.
 */
export const PHASE_CONTENT_COMPONENTS: Record<PhaseId, ComponentType<PhaseViewContext>> = {
  purpose: PurposePhaseContent,
  vision: VisionPhaseContent,
  prd: PrdPhaseContent,
  architecture: ArchitecturePhaseContent,
  architecture_review: ArchitectureReviewPhaseContent,
  implementation: ImplementationPhaseContent,
  review: ReviewPhaseContent,
  release: ReleasePhaseContent,
};

/**
 * Zuordnung der Sidebar-Komponenten zu den Phasen-IDs. Auch hier wird jede
 * Phase direkt mit ihrer zugehörigen Sidebar-Komponente verknüpft.
 */
export const PHASE_SIDEBAR_COMPONENTS: Record<PhaseId, ComponentType<PhaseViewContext>> = {
  purpose: PurposePhaseSidebar,
  vision: VisionPhaseSidebar,
  prd: PrdPhaseSidebar,
  architecture: ArchitecturePhaseSidebar,
  architecture_review: ArchitectureReviewPhaseSidebar,
  implementation: ImplementationPhaseSidebar,
  review: ReviewPhaseSidebar,
  release: ReleasePhaseSidebar,
};
