import React, { Suspense, lazy } from 'react';

interface ChatPanelContainerProps {
  title: string;
  description?: string;
  placeholderTitle?: string;
  placeholderDescription?: string;
  className?: string;
  purposeId: string | null;
  paused: boolean;
  filterValue: string;
  onFilterValueChange: (value: string) => void;
}

const LazyAImarChatPanel = lazy(() => import('../AImarChatPanel'));

export default function ChatPanelContainer({
  title,
  description,
  placeholderTitle,
  placeholderDescription,
  className = '',
  purposeId,
  paused,
  filterValue,
  onFilterValueChange,
}: ChatPanelContainerProps) {
  if (!purposeId) {
    return (
      <section
        className={`rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-6 text-sm text-slate-600 dark:text-slate-300 ${className}`.trim()}
      >
        <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-200">
          {placeholderTitle ?? 'Kein Purpose ausgewählt'}
        </h3>
        <p className="mt-2">
          {placeholderDescription ??
            'Wähle im Kopfbereich einen Purpose aus, um Artefakte zu erstellen und mit dem KI-Produkt Owner zu interagieren.'}
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
        <Suspense
          fallback={
            <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-600 dark:border-slate-600 dark:bg-slate-900/40 dark:text-slate-300">
              Lade Chat …
            </div>
          }
        >
          <LazyAImarChatPanel
            purposeId={purposeId}
            paused={paused}
            filterValue={filterValue}
            onFilterValueChange={onFilterValueChange}
          />
        </Suspense>
      </div>
    </section>
  );
}
