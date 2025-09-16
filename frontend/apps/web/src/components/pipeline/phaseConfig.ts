import {
  Target,
  Lightbulb,
  FileText,
  CircuitBoard,
  ShieldCheck,
  Hammer,
  ClipboardCheck,
  Rocket,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export const PIPELINE_PHASES = [
  { id: 'purpose', title: 'Projektziel', icon: Target },
  { id: 'vision', title: 'Vision', icon: Lightbulb },
  { id: 'prd', title: 'Produktanforderung', icon: FileText },
  { id: 'architecture', title: 'Architektur', icon: CircuitBoard },
  { id: 'architecture_review', title: 'Architektur & Domain Review', icon: ShieldCheck },
  { id: 'implementation', title: 'Implementierung', icon: Hammer },
  { id: 'review', title: 'Review', icon: ClipboardCheck },
  { id: 'release', title: 'Release', icon: Rocket },
] as const;

export type PhaseId = (typeof PIPELINE_PHASES)[number]['id'];

export interface PhaseDefinition {
  id: PhaseId;
  title: string;
  icon: LucideIcon;
}

export const PHASE_DESCRIPTIONS: Record<PhaseId, string> = {
  purpose:
    'Lege das Projektziel fest, indem du einen Purpose auswählst oder erstellst. Dies bestimmt den weiteren Verlauf der Pipeline.',
  vision:
    'Schärfe Vision und Kontext des Projekts. Dokumentiere Rahmenbedingungen, Zielgruppen und Erfolgsfaktoren.',
  prd: 'Erarbeite die Produktanforderungen und stelle sicher, dass alle Stakeholder den gleichen Stand teilen.',
  architecture:
    'Gestalte das technische Fundament. Das Architektur-Blueprint bildet die Basis für eine belastbare Implementierung.',
  architecture_review:
    'Überprüfe Architekturentscheidungen gemeinsam mit Domain-Expert*innen und gib das Review-Dokument frei.',
  implementation:
    'Arbeite die Aufgaben aus dem Task-Graph ab und kollaboriere mit dem Team entlang der Pipeline.',
  review:
    'Koordiniere finale Abstimmungen, teste Ergebnisse und bereite die Freigabe vor.',
  release:
    'Schließe das Projekt ab, indem du alle Artefakte freigibst und das Release kommunizierst.',
};
