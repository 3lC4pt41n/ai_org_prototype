export function normalizePromptContent(input: unknown): string {
  if (input == null) {
    return '';
  }

  if (typeof input === 'string') {
    return input;
  }

  if (typeof input === 'object' && input !== null && 'content' in input) {
    const value = (input as { content?: unknown }).content;
    if (value == null) {
      return '';
    }
    return typeof value === 'string' ? value : String(value);
  }

  return String(input);
}

export function normalizeAgentValue(input: unknown): string | null {
  if (typeof input !== 'string') {
    return null;
  }

  const trimmed = input.trim();
  return trimmed.length > 0 ? trimmed : null;
}
