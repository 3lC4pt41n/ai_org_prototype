import type { ComponentPropsWithoutRef } from "react";
import React, { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";

type MarkdownRendererProps = {
  content: string;
  className?: string;
};

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

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: "default",
      securityLevel: "strict",
    });
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const root = containerRef.current;
    if (!root) return;
    const nodes = root.querySelectorAll<HTMLElement>(".mermaid, .language-mermaid");
    if (nodes.length > 0) {
      void mermaid.run({ nodes });
    }
  }, [content]);

  const containerClassName = [
    "prose",
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
                <div className="mermaid" {...rest}>
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
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;
