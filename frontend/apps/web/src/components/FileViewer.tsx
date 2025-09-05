import ReactMarkdown from "react-markdown";
import Editor from "@monaco-editor/react";

type Props = {
  /** Text-Inhalt, falls es Text ist (md, code, html etc.). */
  text?: string;
  /** Blob-URL für Binärformate (image, pdf...). */
  blobUrl?: string | null;
  /** Originaler Content-Type Header (falls vorhanden). */
  contentType?: string | null;
  /** Dateiname (für Extension-Heuristik). */
  filename?: string | null;
  /** Höhe in px für Code/Markdown/HTML-Viewer. */
  height?: number | string;
};

function ext(filename?: string | null): string {
  if (!filename) return "";
  const m = filename.toLowerCase().match(/\.([a-z0-9]+)$/i);
  return m ? m[1] : "";
}

function isMarkdown(ct?: string | null, fn?: string | null) {
  return ct?.includes("text/markdown") || ext(fn) === "md";
}

function isHTML(ct?: string | null, fn?: string | null) {
  return ct?.includes("text/html") || ext(fn) === "html";
}

function isImage(ct?: string | null, fn?: string | null) {
  return ct?.startsWith("image/") || ["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext(fn));
}

function isPDF(ct?: string | null, fn?: string | null) {
  return ct?.includes("application/pdf") || ext(fn) === "pdf";
}

// Monaco Sprachheuristik
function languageFor(filename?: string | null, ct?: string | null): string | undefined {
  const e = ext(filename);
  const map: Record<string, string> = {
    js: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    json: "json",
    css: "css",
    scss: "scss",
    html: "html",
    md: "markdown",
    py: "python",
    sh: "shell",
    bash: "shell",
    yml: "yaml",
    yaml: "yaml",
    sql: "sql",
    go: "go",
    rs: "rust",
    java: "java",
    kt: "kotlin",
    php: "php",
    rb: "ruby",
    cs: "csharp",
    cpp: "cpp",
    c: "c",
  };
  if (map[e]) return map[e];
  // Content-Type fallback
  if (ct?.includes("json")) return "json";
  if (ct?.includes("xml")) return "xml";
  if (ct?.includes("yaml")) return "yaml";
  if (ct?.includes("markdown")) return "markdown";
  if (ct?.includes("html")) return "html";
  if (ct?.includes("css")) return "css";
  if (ct?.includes("javascript")) return "javascript";
  if (ct?.includes("typescript")) return "typescript";
  return undefined;
}

export default function FileViewer({ text, blobUrl, contentType, filename, height = 480 }: Props) {
  // Markdown
  if (isMarkdown(contentType, filename) && text != null) {
    return (
      <div className="prose max-w-none">
        <ReactMarkdown>{text}</ReactMarkdown>
      </div>
    );
  }

  // HTML (sandboxed)
  if (isHTML(contentType, filename) && text != null) {
    const srcDoc = text;
    return (
      <iframe
        title={filename || "html-preview"}
        sandbox="allow-scripts allow-same-origin"
        style={{ border: "1px solid #e5e7eb", width: "100%", height }}
        srcDoc={srcDoc}
      />
    );
  }

  // Bilder
  if (isImage(contentType, filename) && blobUrl) {
    return (
      <div className="flex items-start justify-start">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={blobUrl} alt={filename || "image"} style={{ maxWidth: "100%", borderRadius: 8 }} />
      </div>
    );
  }

  // PDF
  if (isPDF(contentType, filename) && blobUrl) {
    return (
      <object data={blobUrl} type="application/pdf" width="100%" height={height}>
        <p className="text-sm">
          PDF kann nicht eingebettet angezeigt werden.{' '}
          <a className="text-amber-600 underline" href={blobUrl} target="_blank" rel="noreferrer">
            In neuem Tab öffnen
          </a>
          .
        </p>
      </object>
    );
  }

  // Code/Text in Monaco
  if (text != null) {
    const lang = languageFor(filename, contentType);
    return (
      <div style={{ border: "1px solid #e5e7eb" }}>
        <Editor
          height={height}
          defaultLanguage={lang}
          language={lang}
          value={text}
          options={{
            readOnly: true,
            minimap: { enabled: false },
            lineNumbers: "on",
            wordWrap: "on",
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    );
  }

  // Fallback
  return (
    <p className="text-sm">
      Vorschau nicht verfügbar.{' '}
      {blobUrl && (
        <a className="text-amber-600 underline" href={blobUrl} target="_blank" rel="noreferrer">
          Datei öffnen
        </a>
      )}
    </p>
  );
}
