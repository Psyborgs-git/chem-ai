import { useState, type HTMLAttributes } from "react";
import { Link } from "react-router";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import type { HelpArticle } from "./types";
import "katex/dist/katex.min.css";

function CodeBlock({ children, ...props }: HTMLAttributes<HTMLPreElement>) {
  const [status, setStatus] = useState("");
  return <div className="cs-help-code"><button type="button" className="cs-btn cs-btn--ghost" onClick={(event) => {
    const text = event.currentTarget.parentElement?.querySelector("pre")?.textContent ?? "";
    if (!navigator.clipboard?.writeText) { setStatus("Select the code to copy it."); return; }
    void navigator.clipboard.writeText(text).then(() => setStatus("Copied"), () => setStatus("Select the code to copy it."));
  }}>Copy code</button><span role="status">{status}</span><pre {...props} role="region" aria-label="Code example" tabIndex={0}>{children}</pre></div>;
}

export function HelpMarkdown({ article }: { article: HelpArticle }) {
  const heading: Components["h2"] = ({ node, children, ...props }) => {
    const item = article.headings.find((value) => value.offset === node?.position?.start.offset);
    const Tag = (node?.tagName ?? "h2") as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
    return <Tag {...props} id={item?.id} aria-label={item?.text} tabIndex={-1}>{children}{item && <a className="cs-help-anchor" href={`#${item.id}`} aria-label={`Link to ${item.text}`}>#</a>}</Tag>;
  };
  return <div className="cs-help-prose"><Markdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={{
    h1: heading, h2: heading, h3: heading, h4: heading, h5: heading, h6: heading,
    a: ({ href = "", children }) => {
      const target = article.linkMap[href];
      if (!target) return <span>{children}</span>;
      if (/^https?:\/\//i.test(target)) return <a href={target} target="_blank" rel="noopener noreferrer">{children}<span className="sr-only"> (opens externally)</span><span aria-hidden="true"> ↗</span></a>;
      return <Link to={target}>{children}</Link>;
    },
    pre: ({ node: _node, ...props }) => <CodeBlock {...props} />,
    table: ({ node: _node, ...props }) => <div className="cs-help-table" role="region" aria-label="Reference table" tabIndex={0}><table {...props} /></div>,
    img: ({ alt }) => <span>{alt}</span>,
  }}>{article.markdown}</Markdown></div>;
}
