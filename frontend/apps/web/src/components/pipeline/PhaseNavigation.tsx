import { CheckCircle2, CircleDot, Clock3, Sparkles } from 'lucide-react';
import type { PhaseId } from './phaseConfig';
import type { PhaseNavItem } from './types';

interface PhaseNavigationProps {
  items: PhaseNavItem[];
  onSelect: (id: PhaseId) => void;
}

type Variant = 'completed' | 'current' | 'ready' | 'upcoming';

const VARIANT_STYLES: Record<Variant, {
  button: string;
  iconWrapper: string;
  statusPill: string;
  StatusIcon: typeof CheckCircle2;
}> = {
  completed: {
    button:
      'border-green-200 bg-green-50 text-green-900 hover:border-green-300 hover:bg-green-100 focus-visible:outline-green-600 dark:border-green-500/60 dark:bg-green-500/10 dark:text-green-200',
    iconWrapper:
      'border-green-200 bg-green-100 text-green-700 dark:border-green-500/60 dark:bg-green-500/20 dark:text-green-200',
    statusPill: 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-300',
    StatusIcon: CheckCircle2,
  },
  current: {
    button:
      'border-amber-500 bg-amber-50 text-amber-900 hover:border-amber-500 hover:bg-amber-100 focus-visible:outline-amber-500 dark:border-amber-400 dark:bg-amber-500/10 dark:text-amber-50',
    iconWrapper:
      'border-amber-400 bg-amber-100 text-amber-700 dark:border-amber-300 dark:bg-amber-400/20 dark:text-amber-50',
    statusPill: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-200',
    StatusIcon: Sparkles,
  },
  ready: {
    button:
      'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:bg-slate-800/60',
    iconWrapper:
      'border-slate-200 bg-white text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
    statusPill: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
    StatusIcon: CircleDot,
  },
  upcoming: {
    button:
      'border-slate-200 bg-slate-50 text-slate-500 hover:border-slate-300 hover:bg-slate-100 focus-visible:outline-slate-400 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-800/60',
    iconWrapper:
      'border-slate-200 bg-slate-50 text-slate-400 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400',
    statusPill: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
    StatusIcon: Clock3,
  },
};

export default function PhaseNavigation({ items, onSelect }: PhaseNavigationProps) {
  return (
    <ol className="space-y-2" aria-label="Pipeline-Phasen">
      {items.map((phase) => {
        const variant: Variant = phase.completed
          ? 'completed'
          : phase.isCurrent
            ? 'current'
            : phase.isUpcoming
              ? 'upcoming'
              : 'ready';
        const { button, iconWrapper, statusPill, StatusIcon } = VARIANT_STYLES[variant];
        const PhaseIcon = phase.icon;

        return (
          <li key={phase.id} aria-current={phase.isCurrent ? 'step' : undefined}>
            <button
              type="button"
              onClick={() => onSelect(phase.id)}
              className={`w-full rounded-lg border px-3 py-3 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${button}`}
              aria-label={`${phase.title} – ${phase.statusLabel}`}
            >
              <div className="flex items-center gap-3">
                <span className={`flex h-9 w-9 items-center justify-center rounded-full border ${iconWrapper}`}>
                  <PhaseIcon className="h-4 w-4" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{phase.title}</span>
                    <span className="text-xs text-slate-400">#{phase.index + 1}</span>
                  </div>
                  <div
                    className={`mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusPill}`}
                  >
                    <StatusIcon className="h-3.5 w-3.5" aria-hidden />
                    <span>{phase.statusLabel}</span>
                  </div>
                </div>
              </div>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
