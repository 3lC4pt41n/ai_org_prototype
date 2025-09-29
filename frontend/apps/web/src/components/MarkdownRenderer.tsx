import React, { useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";

type MarkdownRendererProps = {
  content: string;
  className?: string;
};

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, className }) => {
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    mermaid.initialize({
      startOnLoad: true,
      theme: "default",
      securityLevel: "loose",
    });
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const elements = document.querySelectorAll<HTMLElement>(".language-mermaid");
    if (elements.length > 0) {
      mermaid.init(undefined, elements);
    }
  }, [content]);

  return (
    <ReactMarkdown
      className={className}
      remarkPlugins={[remarkGfm]}
      components={{
        code({ inline, className: codeClassName, children, ...props }) {
          const match = /language-(\w+)/.exec(codeClassName || "");
          if (!inline && match && match[1] === "mermaid") {
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
  );
};

export default MarkdownRenderer;
