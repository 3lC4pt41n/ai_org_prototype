const LOCALE = 'de-DE';

type TimestampCarrier = {
  created_at?: string | null;
  createdAt?: string | null;
};

export function extractCreatedAt(source?: TimestampCarrier | null): string | null {
  if (!source) return null;
  const raw = source.created_at ?? source.createdAt ?? null;
  if (!raw) return null;
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

export function normalizeTimestamp(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

export function formatDateTime(value?: string | null, locale: string = LOCALE): string | null {
  const normalized = normalizeTimestamp(value);
  if (!normalized) return null;
  const date = new Date(normalized);
  return date.toLocaleString(locale);
}
