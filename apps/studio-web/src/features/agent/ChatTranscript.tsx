import { lazy, Suspense, useState } from "react";
import { Check, CircleAlert, CircleDashed } from "lucide-react";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import { Message, MessageContent, MessageHeader } from "@/components/ui/message";
import { MessageScrollerItem } from "@/components/ui/message-scroller";
import { Trace, TraceCollapsible, TraceCollapsibleContent, TraceCollapsibleTrigger, TraceDescription, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace";
import { activitySummary, transcriptRows, type ActivityMessage } from "./activity";
const MarkdownPreview = lazy(() => import("../notebooks/MarkdownPreview").then((module) => ({ default: module.MarkdownPreview })));
function MessageBody({ message, onOpenHelp }: { message: ActivityMessage; onOpenHelp?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const longPrompt = message.role === "user" && (message.content.length > 600 || message.content.split("\n").length > 9);
  return <>{longPrompt && !expanded ? <p className="cs-chat-message-preview">{message.content.replace(/\s+/g, " ").trim().slice(0, 360)}…</p> : <Suspense fallback={<p>{message.content}</p>}><MarkdownPreview content={message.content} internalHelpLinks onOpenHelp={onOpenHelp} /></Suspense>}{longPrompt && <Button type="button" variant="link" size="sm" className="cs-chat-show-message" aria-label={expanded ? "Collapse message" : "Show full message"} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? "Show less" : "Show more"}</Button>}</>;
}
const parsed = (content?: string) => { if (!content) return undefined; try { return JSON.parse(content); } catch { return content; } };
type Tool = Extract<ReturnType<typeof transcriptRows>[number], { type: "activity" }>["tools"][number];
function ActivityStep({ tool, summary }: { tool: Tool; summary: ReturnType<typeof activitySummary> }) {
  const [showData, setShowData] = useState(false);
  return <TraceCollapsible open={showData} onOpenChange={setShowData}><TraceCollapsibleTrigger aria-label={`${summary.title} — technical details`}><TraceLine status={summary.failed ? "error" : !tool.result ? "running" : undefined}><TraceIcon>{summary.failed ? <CircleAlert /> : tool.result ? <Check /> : <CircleDashed />}</TraceIcon><TraceTitle>{summary.title}</TraceTitle><TraceDescription>{summary.detail}</TraceDescription></TraceLine></TraceCollapsibleTrigger><TraceCollapsibleContent>{showData && <pre className="cs-chat-tool-data">{JSON.stringify({ tool: tool.name, arguments: parsed(tool.call?.content), result: parsed(tool.result?.content) }, null, 2)}</pre>}</TraceCollapsibleContent></TraceCollapsible>;
}
function ActivityBlock({ row, working }: { row: Extract<ReturnType<typeof transcriptRows>[number], { type: "activity" }>; working: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const summaries = row.tools.map(activitySummary), failed = summaries.filter((summary) => summary.failed).length;
  const label = working ? "Working" : failed ? "Steps need attention" : "Research activity";
  return <Trace className="cs-chat-trace"><TraceCollapsible open={expanded} onOpenChange={setExpanded}><TraceCollapsibleTrigger aria-label={`${label} · ${row.tools.length} ${row.tools.length === 1 ? "step" : "steps"}`}><TraceLine status={failed ? "error" : working ? "running" : undefined}><TraceIcon>{working ? <CircleDashed /> : failed ? <CircleAlert /> : <Check />}</TraceIcon><TraceTitle>{label}</TraceTitle><TraceDescription>{row.tools.length} {row.tools.length === 1 ? "step" : "steps"}</TraceDescription></TraceLine></TraceCollapsibleTrigger><TraceCollapsibleContent>{expanded && <Trace>{row.tools.map((tool, index) => <ActivityStep key={tool.id} tool={tool} summary={summaries[index]} />)}</Trace>}</TraceCollapsibleContent></TraceCollapsible></Trace>;
}
export function ChatTranscript({ messages, activeRunId, onOpenHelp }: { messages: (ActivityMessage & { runId?: string })[]; activeRunId?: string; onOpenHelp?: () => void }) {
  const rows = transcriptRows(messages), lastActivity = [...rows].reverse().find((row) => row.type === "activity");
  return <>{rows.map((row) => row.type === "message" ? <MessageScrollerItem key={row.message.id} messageId={row.message.id} scrollAnchor={row.message.role === "user"} className="cs-chat-turn"><Message align={row.message.role === "user" ? "end" : "start"} className={`cs-chat-message cs-chat-message--${row.message.role}${row.message.kind === "status" ? " is-status" : ""}`}><MessageContent><MessageHeader className="sr-only">{row.message.role === "user" ? "You" : row.message.role === "assistant" ? "Agent" : row.message.role}</MessageHeader><Bubble align={row.message.role === "user" ? "end" : "start"} variant={row.message.role === "user" ? "muted" : "ghost"}><BubbleContent><MessageBody message={row.message} onOpenHelp={onOpenHelp} /></BubbleContent></Bubble></MessageContent></Message></MessageScrollerItem> : <MessageScrollerItem key={row.id} messageId={`activity-${row.id}`} className="cs-chat-turn"><ActivityBlock row={row} working={!!activeRunId && (row.runId ? row.runId === activeRunId : lastActivity?.id === row.id)} /></MessageScrollerItem>)}</>;
}
