import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Link } from "react-router";
import { isStudioHelpLink } from "../help/links";
import "katex/dist/katex.min.css";

export function MarkdownPreview({ content, internalHelpLinks = false, onOpenHelp }: { content: string; internalHelpLinks?: boolean; onOpenHelp?: () => void }) {
  return <div className="cs-notebook-prose"><Markdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={{
    a: ({ children, href = "", ...props }) => internalHelpLinks && isStudioHelpLink(href)
      ? <Link to={href} onClick={(event) => { if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) onOpenHelp?.(); }}>{children}</Link>
      : <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
    img: ({ src, alt }) => <a href={src} target="_blank" rel="noopener noreferrer">View image{alt ? `: ${alt}` : ""}</a>,
  }}>{content}</Markdown></div>;
}
