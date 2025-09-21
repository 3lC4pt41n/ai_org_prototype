import type { ComponentType } from 'react';
import type { PhaseId } from './phaseConfig';
import type { PhaseViewContext } from './types';

// Direktimporte aller Phasen-Komponenten
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

// Einheitlicher Typ für Komponenten
export type PhaseComponent = ComponentType<PhaseViewContext>;

// Map für die Content-Komponenten
export const PHASE_CONTENT_COMPONENTS: Record<PhaseId, PhaseComponent> = {
  purpose: PurposePhaseContent,
  vision: VisionPhaseContent,
  prd: PrdPhaseContent,
  architecture: ArchitecturePhaseContent,
  architecture_review: ArchitectureReviewPhaseContent,
  implementation: ImplementationPhaseContent,
  review: ReviewPhaseContent,
  release: ReleasePhaseContent,
};

// Map für die Sidebar-Komponenten
export const PHASE_SIDEBAR_COMPONENTS: Record<PhaseId, PhaseComponent> = {
  purpose: PurposePhaseSidebar,
  vision: VisionPhaseSidebar,
  prd: PrdPhaseSidebar,
  architecture: ArchitecturePhaseSidebar,
  architecture_review: ArchitectureReviewPhaseSidebar,
  implementation: ImplementationPhaseSidebar,
  review: ReviewPhaseSidebar,
  release: ReleasePhaseSidebar,
};
