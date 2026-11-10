import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const CITATION_RE = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

function linkCitations(text: string): string {
  return text.replace(CITATION_RE, (_m, group: string) =>
    group
      .split(",")
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(""),
  );
}

export function stripCitations(text: string): string {
  return text.replace(CITATION_RE, "").replace(/ +([.,;:])/g, "$1");
}

export default function AnswerText({
  text,
  streaming = false,
  onCite,
}: {
  text: string;
  streaming?: boolean;
  onCite?: (n: number) => void;
}) {
  return (
    <div className={`answer${streaming ? " caret" : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#cite-")) {
              const n = Number(href.slice(6));
              return (
                <sup className="cite">
                  <button type="button" onClick={() => onCite?.(n)} aria-label={`Show source ${n}`}>
                    {n}
                  </button>
                </sup>
              );
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  );
}
