export type PipelineLocale = 'de';

type ArtifactPreviewCopy = {
  defaultEmptyMessage: string;
  readOnlyNotice: string;
  emptyFallback: string;
  notDisplayable: string;
  downloadPrimary: string;
  downloadSecondary: string;
  statusReleased: string;
  statusDraft: string;
  updatedAt: string;
  loadError: string;
  previousLoadError: string;
  refreshError: string;
};

type ChatCopy = {
  heading: string;
  description: string;
  placeholderInactivePurpose: string;
  placeholderInactivePurposeTitle: string;
  placeholderNoArtifact: string;
  loadMore: string;
  noMessages: string;
  loading: string;
  intent: {
    approval: string;
    question: string;
    feedback: string;
  };
  textareaLabel: string;
  textareaPlaceholder: string;
  send: string;
  approve: string;
  pausedNotice: string;
  loadError: string;
  submitError: string;
  approveSuccess: string;
  refreshError: string;
};

type PipelineCopy = {
  artifactPreview: ArtifactPreviewCopy;
  chat: ChatCopy;
};

const de: PipelineCopy = {
  artifactPreview: {
    defaultEmptyMessage: 'Für diese Phase liegt noch kein Artefakt vor.',
    readOnlyNotice: 'Nur-Lesen: Dieses Artefakt dient als Referenz und kann nicht bearbeitet werden.',
    emptyFallback: 'Das Artefakt enthält derzeit keinen darstellbaren Text.',
    notDisplayable: 'Dieses Artefakt kann nicht direkt im Browser angezeigt werden.',
    downloadPrimary: 'Datei herunterladen',
    downloadSecondary: 'Original herunterladen',
    statusReleased: 'freigegeben',
    statusDraft: 'in Arbeit',
    updatedAt: 'Aktualisiert am',
    loadError: 'Artefakt konnte nicht geladen werden.',
    previousLoadError: 'Referenzartefakt konnte nicht geladen werden.',
    refreshError: 'Artefakt konnte nicht aktualisiert werden.',
  },
  chat: {
    heading: 'Feedback & Fragen',
    description:
      'Alle Rückmeldungen werden automatisch dieser Phase zugeordnet und im Artefakt gespeichert.',
    placeholderInactivePurpose: 'Wähle zunächst einen Purpose aus, um den Chat für diese Phase zu aktivieren.',
    placeholderInactivePurposeTitle: 'Kein Purpose ausgewählt',
    placeholderNoArtifact: 'Sobald ein Artefakt vorliegt, kannst du hier Fragen und Feedback teilen.',
    loadMore: 'Ältere Nachrichten laden',
    noMessages: 'Noch keine Nachrichten für dieses Artefakt.',
    loading: 'Nachrichten werden geladen…',
    intent: {
      approval: 'Freigabe',
      question: 'Frage',
      feedback: 'Feedback',
    },
    textareaLabel: 'Feedback / Rückfrage',
    textareaPlaceholder: 'Schreibe eine Rückmeldung oder Frage zur Phase…',
    send: 'Senden',
    approve: 'Freigeben',
    pausedNotice:
      'Der Purpose ist pausiert. Du kannst Feedback hinterlassen, aber Antworten erfolgen erst nach dem Fortsetzen.',
    loadError: 'Chatverlauf konnte nicht geladen werden.',
    submitError: 'Nachricht konnte nicht gesendet werden.',
    approveSuccess: 'Artefakt wurde freigegeben.',
    refreshError: 'Nachrichten konnten nicht aktualisiert werden.',
  },
};

const locales: Record<PipelineLocale, PipelineCopy> = {
  de,
};

export function usePipelineCopy(locale: PipelineLocale = 'de'): PipelineCopy {
  return locales[locale];
}
