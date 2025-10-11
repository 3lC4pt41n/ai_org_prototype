import { Download, FileText, FileWarning } from 'lucide-react';
import type { ArtifactDetails } from '../../api/api.artifacts';
import { formatDateTime } from '../../lib/datetime';
import { usePipelineCopy } from '../../i18n/pipeline';

export interface PhaseArtifactPreviewData
  extends Pick<ArtifactDetails, 'id' | 'name' | 'path' | 'content' | 'text' | 'markdown' | 'url' | 'media_type' | 'released' | 'created_at'> {}

interface PhaseArtifactPreviewProps {
  title: string;
  phaseLabel?: string;
  artifact?: PhaseArtifactPreviewData | null;
  isLoading?: boolean;
  emptyMessage?: string;
  readOnly?: boolean;
}

function resolveDisplayText(artifact?: PhaseArtifactPreviewData | null): string | null {
  if (!artifact) return null;
  if (artifact.content && typeof artifact.content === 'string') return artifact.content;
  if (artifact.text && typeof artifact.text === 'string') return artifact.text;
  if (artifact.markdown && typeof artifact.markdown === 'string') return artifact.markdown;
  return null;
}

function isTextualMedia(artifact?: PhaseArtifactPreviewData | null): boolean {
  const mediaType = artifact?.media_type?.toLowerCase();
  if (!mediaType) return !!resolveDisplayText(artifact);
  return (
    mediaType.startsWith('text/') ||
    mediaType.includes('json') ||
    mediaType.includes('xml') ||
    mediaType.includes('yaml') ||
    mediaType.includes('markdown') ||
    mediaType.includes('javascript')
  );
}

function StatusBadge({ released, labelReleased, labelDraft }: { released?: boolean; labelReleased: string; labelDraft: string }) {
  const label = released ? labelReleased : labelDraft;
  const classes = released
    ? 'bg-emerald-100 text-emerald-700 border border-emerald-200'
    : 'bg-amber-100 text-amber-700 border border-amber-200';
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${classes}`}>
      {label}
    </span>
  );
}

export default function PhaseArtifactPreview({
  title,
  phaseLabel,
  artifact,
  isLoading = false,
  emptyMessage,
  readOnly = false,
}: PhaseArtifactPreviewProps) {
  const { artifactPreview } = usePipelineCopy();
  const textualContent = resolveDisplayText(artifact);
  const hasTextualContent = textualContent && textualContent.trim().length > 0;
  const isText = isTextualMedia(artifact);
  const updatedAt = formatDateTime(artifact?.created_at ?? null);
  const fileName = artifact?.path?.split('/').pop() ?? artifact?.name ?? null;
  const resolvedEmptyMessage = emptyMessage ?? artifactPreview.defaultEmptyMessage;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          {phaseLabel && (
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {phaseLabel}
            </p>
          )}
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
          {fileName && (
            <p className="text-xs text-slate-500 dark:text-slate-400">{fileName}</p>
          )}
        </div>
        {artifact && (
          <StatusBadge
            released={artifact.released}
            labelReleased={artifactPreview.statusReleased}
            labelDraft={artifactPreview.statusDraft}
          />
        )}
      </header>

      {readOnly && (
        <p className="mt-3 rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
          {artifactPreview.readOnlyNotice}
        </p>
      )}

      {isLoading ? (
        <div className="mt-6 space-y-3">
          <div className="h-4 w-1/3 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
          <div className="h-4 w-full animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
          <div className="h-4 w-5/6 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
        </div>
      ) : artifact ? (
        <div className="mt-6 space-y-4">
          {hasTextualContent && isText ? (
            <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed text-slate-800 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100">
              {textualContent}
            </pre>
          ) : (
            <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-200">
              <div className="mt-0.5 text-slate-500 dark:text-slate-400">
                {isText ? <FileText className="h-5 w-5" /> : <FileWarning className="h-5 w-5" />}
              </div>
              <div className="space-y-1">
                <p>{isText ? artifactPreview.emptyFallback : artifactPreview.notDisplayable}</p>
                {artifact.url && (
                  <a
                    href={artifact.url}
                    className="inline-flex items-center gap-2 text-sm font-medium text-indigo-600 hover:text-indigo-500"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Download className="h-4 w-4" /> {artifactPreview.downloadPrimary}
                  </a>
                )}
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-4 text-xs text-slate-500 dark:text-slate-400">
            {updatedAt && (
              <span>
                {artifactPreview.updatedAt} {updatedAt}
              </span>
            )}
            {artifact.url && (
              <a
                href={artifact.url}
                className="inline-flex items-center gap-2 font-medium text-indigo-600 hover:text-indigo-500"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Download className="h-4 w-4" /> {artifactPreview.downloadSecondary}
              </a>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-6 flex items-center gap-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-300">
          <FileWarning className="h-5 w-5" />
          <span>{resolvedEmptyMessage}</span>
        </div>
      )}
    </section>
  );
}
