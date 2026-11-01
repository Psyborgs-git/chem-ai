import { lazy, Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { activitySummary, transcriptRows, type ActivityMessage } from "./activity";
const MarkdownPreview = lazy(() => import("../notebooks/MarkdownPreview").then((module) => ({ default: module.MarkdownPreview })));
function MessageBody({ message }: { message: ActivityMessage }) {
  const [expanded, setExpanded] = useState(false);
  const longPrompt = message.role === "user" && (message.content.length > 600 || message.content.split("\n").length > 9);
  return <>{longPrompt && !expanded ? <p className="cs-chat-message-preview">{message.content.replace(/\s+/g, " ").trim().slice(0, 360)}…</p> : <Suspense fallback={<p>{message.content}</p>}><MarkdownPreview content={message.content} /></Suspense>}{longPrompt && <Button type="button" variant="link" size="sm" className="cs-chat-show-message" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? "Show less" : "Show full message"}</Button>}</>;
}
const parsed = (content?: string) => { if (!content) return undefined; try { return JSON.parse(content); } catch { return content; } };
type Tool = Extract<ReturnType<typeof transcriptRows>[number], { type: "activity" }>["tools"][number];
function ActivityStep({ tool, summary }: { tool: Tool; summary: ReturnType<typeof activitySummary> }) {
  const [showData, setShowData] = useState(false);
  return <li data-state={summary.failed ? "failed" : tool.result ? "done" : "working"}><div className="cs-chat-step-caption"><span aria-hidden="true">{summary.failed ? "!" : tool.result ? "✓" : "·"}</span><div><strong>{summary.title}</strong><small>{summary.detail}</small></div></div><details className="cs-chat-step-data" onToggle={(event) => setShowData(event.currentTarget.open)}><summary>Technical details</summary>{showData && <pre>{JSON.stringify({ tool: tool.name, arguments: parsed(tool.call?.content), result: parsed(tool.result?.content) }, null, 2)}</pre>}</details></li>;
}
function ActivityBlock({ row, working }: { row: Extract<ReturnType<typeof transcriptRows>[number], { type: "activity" }>; working: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const summaries = row.tools.map(activitySummary), failed = summaries.filter((summary) => summary.failed).length;
  return <details className={`cs-chat-activity${working ? " is-working" : ""}`} onToggle={(event) => setExpanded(event.currentTarget.open)}><summary><span className="cs-chat-activity-icon" aria-hidden="true">{working ? "◌" : failed ? "!" : "✓"}</span><span><strong>{working ? "Working" : "Activity"} <span>· {row.tools.length} {row.tools.length === 1 ? "step" : "steps"}</span></strong><small>{failed ? `${failed} ${failed === 1 ? "step needs" : "steps need"} attention` : working ? summaries.at(-1)?.title : summaries.slice(0, 2).map((summary) => summary.title).join(" · ")}</small></span><span className="cs-chat-activity-chevron" aria-hidden="true">⌄</span></summary>{expanded && <ol>{row.tools.map((tool, index) => <ActivityStep key={tool.id} tool={tool} summary={summaries[index]} />)}</ol>}</details>;
}
export function ChatTranscript({ messages, activeRunId }: { messages: (ActivityMessage & { runId?: string })[]; activeRunId?: string }) {
  const rows = transcriptRows(messages), lastActivity = [...rows].reverse().find((row) => row.type === "activity");
  return <>{rows.map((row) => row.type === "message" ? <article key={row.message.id} className={`cs-chat-message cs-chat-message--${row.message.role}${row.message.kind === "status" ? " is-status" : ""}`}><span className="cs-chat-message-author">{row.message.role === "user" ? "You" : row.message.role === "assistant" ? "Agent" : row.message.role}</span><div className="cs-chat-message-content"><MessageBody message={row.message} /></div></article> : <ActivityBlock key={row.id} row={row} working={!!activeRunId && (row.runId ? row.runId === activeRunId : lastActivity?.id === row.id)} />)}</>;
}
