import type { ComponentPropsWithoutRef } from "react";
import React, { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";

type MarkdownRendererProps = {
  content: string;
  className?: string;
};

function unwrapOuterMarkdownFence(input: string): string {
  const text = (input || "").trim();
  const match = text.match(/^```([a-zA-Z0-9_-]+)?\s*\n([\s\S]*?)\n```$/);
  if (!match) return input;
  const language = (match[1] || "").toLowerCase();
  if (language && !["md", "markdown", "txt", "text"].includes(language)) {
    return input;
  }
  return match[2] ?? input;
}

/**
 * MarkdownRenderer
 * ----------------
 * Renders Markdown including Mermaid diagrams.
 *
 * Usage:
 *   <MarkdownRenderer content={artifact.markdown} />
 */
const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, className }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const normalizedContent = unwrapOuterMarkdownFence(content);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: "neutral",
      securityLevel: "strict",
      flowchart: {
        useMaxWidth: true,
      },
    });
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const root = containerRef.current;
    if (!root) return;
    const nodes = root.querySelectorAll<HTMLElement>(".mermaid");
    if (nodes.length > 0) {
      void mermaid.run({ nodes });
    }
  }, [normalizedContent]);

  const containerClassName = [
    "pipeline-markdown",
    "prose",
    "prose-slate",
    "max-w-none",
    "overflow-auto",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div ref={containerRef} className={containerClassName}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({
            children,
            ...rest
          }: ComponentPropsWithoutRef<"pre">) {
            const child = Array.isArray(children) ? children[0] : children;
            const childClassName = React.isValidElement<{ className?: string }>(child)
              ? child.props.className
              : undefined;
            if (
              typeof childClassName === "string" &&
              /language-mermaid/i.test(childClassName)
            ) {
              return <>{children}</>;
            }
            return <pre {...rest}>{children}</pre>;
          },
          code({
            inline,
            className: codeClassName,
            children,
            node: _node,
            ...rest
          }: ComponentPropsWithoutRef<"code"> & {
            inline?: boolean;
            node?: unknown;
          }) {
            const match = /language-(\w+)/.exec(codeClassName || "");
            if (!inline && match?.[1]?.toLowerCase() === "mermaid") {
              return (
                <div
                  className="mermaid not-prose my-4 overflow-x-auto rounded-md border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-950/40"
                  {...rest}
                >
                  {String(children).replace(/\n$/, "")}
                </div>
              );
            }
            return (
              <code className={codeClassName} {...rest}>
                {children}
              </code>
            );
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;
