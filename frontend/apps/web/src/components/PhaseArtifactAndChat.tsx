import { useEffect, useMemo, useState } from 'react';
import { toast } from 'react-hot-toast';
import {
  getArtifactById,
  listArtifactsByPurpose,
  type ArtifactDetails,
  type ArtifactSummary,
} from '../api/api.artifacts';
import { extractCreatedAt } from '../lib/datetime';
import { usePipelineCopy } from '../i18n/pipeline';
import ChatPanelContainer from './pipeline/ChatPanelContainer';
import { type ArtifactChatContext } from './AImarChatPanel';
import PhaseArtifactPreview, {
  type PhaseArtifactPreviewData,
} from './pipeline/PhaseArtifactPreview';

export type PreviousArtifactConfig = {
  id: string;
  title: string;
  phaseLabel?: string;
};

type PhaseArtifactAndChatProps = {
  purposeId: string | null;
  phaseKey: string;
  phaseTitle: string;
  artifactId?: string | null;
  artifactName?: string | null;
  paused?: boolean;
  previousArtifacts?: PreviousArtifactConfig[];
  emptyMessage?: string;
  onApproved?: () => void;
};

function normalizeArtifact(details: ArtifactDetails | null): PhaseArtifactPreviewData | null {
  if (!details) return null;
  return {
    id: details.id,
    name: details.name ?? null,
    path: details.path ?? null,
    content: details.content ?? null,
    text: details.text ?? null,
    markdown: details.markdown ?? null,
    url: details.url ?? null,
    media_type: (details as any).media_type ?? null,
    released: details.released ?? false,
    created_at: details.created_at ?? null,
  };
}

function buildArtifactTitle(
  explicitName: string | null | undefined,
  artifact: PhaseArtifactPreviewData | null,
  phaseTitle: string,
): string {
  if (explicitName && explicitName.trim().length > 0) return explicitName;
  if (artifact?.name && artifact.name.trim().length > 0) return artifact.name;
  if (artifact?.path) {
    const filename = artifact.path.split('/').pop();
    if (filename) return filename;
  }
  return `${phaseTitle}-Artefakt`;
}

export default function PhaseArtifactAndChat({
  purposeId,
  phaseKey,
  phaseTitle,
  artifactId,
  artifactName,
  paused = false,
  previousArtifacts = [],
  emptyMessage = 'Noch kein Artefakt für diese Phase vorhanden.',
  onApproved,
}: PhaseArtifactAndChatProps) {
  const { artifactPreview, chat } = usePipelineCopy();
  const [resolvedArtifactId, setResolvedArtifactId] = useState<string | null>(artifactId ?? null);
  const [currentDetails, setCurrentDetails] = useState<ArtifactDetails | null>(null);
  const [isLoadingCurrent, setIsLoadingCurrent] = useState<boolean>(false);
  const [autoSelectLoading, setAutoSelectLoading] = useState<boolean>(false);
  const [prevDetails, setPrevDetails] = useState<
    Array<{ config: PreviousArtifactConfig; details: ArtifactDetails | null; loading: boolean }>
  >([]);

  useEffect(() => {
    setResolvedArtifactId(artifactId ?? null);
  }, [artifactId]);

  useEffect(() => {
    if (artifactId || !purposeId) return;
    let canceled = false;
    setAutoSelectLoading(true);
    async function pickLatestArtifact() {
      try {
        const list = await listArtifactsByPurpose(purposeId);
        if (canceled) return;
        if (!list.length) {
          setResolvedArtifactId(null);
          return;
        }
        const sorted = [...list].sort((a, b) => {
          const aTs = new Date(extractCreatedAt(a) ?? 0).getTime();
          const bTs = new Date(extractCreatedAt(b) ?? 0).getTime();
          return aTs - bTs;
        });
        const phaseNeedle = phaseKey.toLowerCase();
        const match = sorted.find((item) => {
          const candidate = (item.name || (item as ArtifactSummary).path || '').toLowerCase();
          return candidate.includes(phaseNeedle);
        });
        const best = match ?? sorted[sorted.length - 1];
        setResolvedArtifactId(best.id);
      } catch (error) {
        console.error('Unable to auto-select artifact', error);
        if (!canceled) {
          toast.error(artifactPreview.loadError);
          setResolvedArtifactId(null);
        }
      } finally {
        if (!canceled) {
          setAutoSelectLoading(false);
        }
      }
    }
    void pickLatestArtifact();
    return () => {
      canceled = true;
    };
  }, [artifactId, purposeId, phaseKey]);

  useEffect(() => {
    if (!resolvedArtifactId) {
      setCurrentDetails(null);
      setIsLoadingCurrent(false);
      return;
    }
    let canceled = false;
    setIsLoadingCurrent(true);
    async function loadDetails() {
      try {
        const details = await getArtifactById(resolvedArtifactId);
        if (!canceled) {
          setCurrentDetails(details);
        }
      } catch (error) {
        console.error('Unable to load artifact details', error);
        if (!canceled) {
          toast.error(artifactPreview.loadError);
          setCurrentDetails(null);
        }
      } finally {
        if (!canceled) {
          setIsLoadingCurrent(false);
        }
      }
    }
    void loadDetails();
    return () => {
      canceled = true;
    };
  }, [resolvedArtifactId]);

  useEffect(() => {
    if (!previousArtifacts.length) {
      setPrevDetails([]);
      return;
    }
    let canceled = false;
    setPrevDetails(previousArtifacts.map((config) => ({ config, details: null, loading: true })));
    async function loadPrevious() {
      try {
        const results = await Promise.all(
          previousArtifacts.map(async (config) => {
            try {
              const details = await getArtifactById(config.id);
              return { config, details, loading: false } as const;
            } catch (error) {
              console.error('Unable to load referenced artifact', error);
              toast.error(artifactPreview.previousLoadError);
              return { config, details: null, loading: false } as const;
            }
          }),
        );
        if (!canceled) {
          setPrevDetails(results);
        }
      } catch (error) {
        console.error('Unable to load previous artifacts', error);
        if (!canceled) {
          toast.error(artifactPreview.previousLoadError);
          setPrevDetails(previousArtifacts.map((config) => ({ config, details: null, loading: false })));
        }
      }
    }
    void loadPrevious();
    return () => {
      canceled = true;
    };
  }, [
    JSON.stringify(
      previousArtifacts.map((item) => ({
        id: item.id,
        title: item.title,
        phaseLabel: item.phaseLabel ?? '',
      })),
    ),
  ]);

  const normalizedCurrent = useMemo(() => normalizeArtifact(currentDetails), [currentDetails]);
  const artifactTitle = useMemo(
    () => buildArtifactTitle(artifactName, normalizedCurrent, phaseTitle),
    [artifactName, normalizedCurrent, phaseTitle],
  );
  const resolvedEmptyMessage = emptyMessage ?? artifactPreview.defaultEmptyMessage;

  async function refreshCurrentArtifact() {
    if (!resolvedArtifactId) return;
    try {
      const details = await getArtifactById(resolvedArtifactId);
      setCurrentDetails(details);
    } catch (error) {
      console.error('Unable to refresh artifact', error);
      toast.error(artifactPreview.refreshError);
    }
  }

  const artifactContext: ArtifactChatContext | null = resolvedArtifactId
    ? {
        artifactId: resolvedArtifactId,
        artifactTitle,
        phaseLabel: `Phase: ${phaseTitle}`,
        phaseKey,
        artifactReleased: normalizedCurrent?.released,
      }
    : null;

  return (
    <div className="space-y-6">
      {prevDetails.map(({ config, details, loading }) => (
        <PhaseArtifactPreview
          key={config.id}
          title={config.title}
          phaseLabel={config.phaseLabel ?? `Phase: ${config.title}`}
          artifact={normalizeArtifact(details)}
          isLoading={loading}
          readOnly
          emptyMessage={artifactPreview.previousLoadError}
        />
      ))}

      <PhaseArtifactPreview
        title={artifactTitle}
        phaseLabel={`Phase: ${phaseTitle}`}
        artifact={normalizedCurrent}
        isLoading={isLoadingCurrent || autoSelectLoading}
        emptyMessage={resolvedEmptyMessage}
      />

      <ChatPanelContainer
        title={chat.heading}
        description={chat.description}
        purposeId={purposeId}
        paused={paused}
        artifactContext={artifactContext}
        onFeedbackSubmitted={refreshCurrentArtifact}
        onArtifactApproved={onApproved}
      />
    </div>
  );
}
