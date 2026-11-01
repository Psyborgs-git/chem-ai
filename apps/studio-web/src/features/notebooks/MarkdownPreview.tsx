import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

export function MarkdownPreview({ content }: { content: string }) {
  return <div className="cs-notebook-prose"><Markdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={{ a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>, img: ({ src, alt }) => <a href={src} target="_blank" rel="noopener noreferrer">View image{alt ? `: ${alt}` : ""}</a> }}>{content}</Markdown></div>;
}
