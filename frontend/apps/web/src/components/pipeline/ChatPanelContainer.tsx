import React, { Suspense, lazy } from 'react';
import type { ReactNode } from 'react';

import type { ArtifactChatContext } from '../AImarChatPanel';
import { usePipelineCopy } from '../../i18n/pipeline';

const AImarChatPanel = lazy(() => import('../AImarChatPanel'));

interface ChatPanelContainerProps {
  title: string;
  description?: string;
  placeholderTitle?: string;
  placeholderDescription?: string;
  className?: string;
  purposeId: string | null;
  paused?: boolean;
  filterValue?: string;
  onFilterValueChange?: (value: string) => void;
  artifactContext?: ArtifactChatContext | null;
  onFeedbackSubmitted?: () => void;
  onArtifactApproved?: () => void;
  artifactPlaceholder?: ReactNode;
}

export default function ChatPanelContainer({
  title,
  description,
  placeholderTitle,
  placeholderDescription,
  className = '',
  purposeId,
  paused = false,
  filterValue,
  onFilterValueChange,
  artifactContext,
  onFeedbackSubmitted,
  onArtifactApproved,
  artifactPlaceholder,
}: ChatPanelContainerProps) {
  const { chat } = usePipelineCopy();
  const legacyMode = artifactContext === undefined;

  if (!purposeId) {
    return (
      <section
        className={`rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300 ${className}`.trim()}
      >
        <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">
          {placeholderTitle ?? chat.placeholderInactivePurposeTitle}
        </h3>
        <p className="mt-2">
          {placeholderDescription ?? chat.placeholderInactivePurpose}
        </p>
      </section>
    );
  }

  return (
    <section
      className={`rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 sm:p-6 shadow-sm ${className}`.trim()}
    >
      <div className="flex flex-col gap-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">{title}</h3>
          {description && (
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{description}</p>
          )}
        </div>
        {artifactContext ? (
          <Suspense
            fallback={
              <div className="flex min-h-[200px] items-center justify-center text-sm text-slate-500">
                {chat.loading}
              </div>
            }
          >
            <AImarChatPanel
              purposeId={purposeId}
              paused={paused}
              filterValue={filterValue}
              onFilterValueChange={onFilterValueChange}
              artifactContext={artifactContext}
              onFeedbackSubmitted={onFeedbackSubmitted}
              onArtifactApproved={onArtifactApproved}
            />
          </Suspense>
        ) : legacyMode ? (
          <Suspense
            fallback={
              <div className="flex min-h-[200px] items-center justify-center text-sm text-slate-500">
                {chat.loading}
              </div>
            }
          >
            <AImarChatPanel
              purposeId={purposeId}
              paused={paused}
              filterValue={filterValue}
              onFilterValueChange={onFilterValueChange}
            />
          </Suspense>
        ) : artifactPlaceholder ? (
          artifactPlaceholder
        ) : (
          <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-300">
            {chat.placeholderNoArtifact}
          </div>
        )}
      </div>
    </section>
  );
}
