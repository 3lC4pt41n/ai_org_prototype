// @ts-nocheck
import { jest } from '@jest/globals';
import React from 'react';
import { render, waitFor } from '@testing-library/react';

const mermaidStub = {
  initialize: jest.fn(),
  run: jest.fn().mockImplementation(({ nodes }) => {
    for (const node of nodes) {
      node.innerHTML = '<svg role="img" aria-label="diagram"></svg>';
    }
    return Promise.resolve();
  }),
};

// Hinweis: Mermaid wird in diesem Test via jest.mock() stubbed.
jest.unstable_mockModule('mermaid', () => ({
  __esModule: true,
  default: mermaidStub,
}));

const MD = [
  '```mermaid',
  'flowchart LR',
  '  A[Start] --> B{Mermaid v11};',
  '  B -->|OK| C[SVG rendered];',
  '```',
].join('\n');

describe('MarkdownRenderer – Mermaid', () => {
  test('renders a mermaid diagram into SVG', async () => {
    const { default: MarkdownRenderer } = await import('../components/MarkdownRenderer');
    await import('mermaid');

    const { container } = render(<MarkdownRenderer content={MD} />);

    await waitFor(() => {
      const mermaidHost = container.querySelector('.mermaid');
      expect(mermaidHost).toBeTruthy();
      const svg = mermaidHost?.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });
  });
});
