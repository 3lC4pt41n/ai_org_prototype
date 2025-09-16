import type { ComponentType } from 'react';
import type { PhaseId } from '../phaseConfig';
import type { PhaseViewContext } from '../types';
import {
  PurposePhaseContent,
  PurposePhaseSidebar,
} from './PurposePhase';
import {
  VisionPhaseContent,
  VisionPhaseSidebar,
} from './VisionPhase';
import { PrdPhaseContent, PrdPhaseSidebar } from './PrdPhase';
import {
  ArchitecturePhaseContent,
  ArchitecturePhaseSidebar,
} from './ArchitecturePhase';
import {
  ArchitectureReviewPhaseContent,
  ArchitectureReviewPhaseSidebar,
} from './ArchitectureReviewPhase';
import {
  ImplementationPhaseContent,
  ImplementationPhaseSidebar,
} from './ImplementationPhase';
import { ReviewPhaseContent, ReviewPhaseSidebar } from './ReviewPhase';
import { ReleasePhaseContent, ReleasePhaseSidebar } from './ReleasePhase';

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
