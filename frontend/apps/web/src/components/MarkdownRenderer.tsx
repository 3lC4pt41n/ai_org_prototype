import React, { useEffect } from "react";
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
  useEffect(() => {
    mermaid.initialize({
      startOnLoad: true,
      theme: "default",
      securityLevel: "loose",
    });
    const nodes = document.querySelectorAll<HTMLElement>(".language-mermaid");
    if (nodes.length > 0) {
      void mermaid.init(undefined, nodes);
    }
  }, [content]);

  const containerClassName = className ? `${className} prose max-w-none` : "prose max-w-none";

  return (
    <div className={containerClassName}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ inline, className: codeClassName, children, ...props }) {
            const match = /language-(\w+)/.exec(codeClassName || "");
            if (!inline && match?.[1] === "mermaid") {
              return (
                <div className="mermaid" {...props}>
                  {String(children).replace(/\n$/, "")}
                </div>
              );
            }
            return (
              <code className={codeClassName} {...props}>
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
