import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { useLocation } from "react-router";
import { ArrowDownLeft, ArrowUp, Expand, History, Plus, RefreshCw, Settings2, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { StudioIcon, TechnicalDetails } from "../../components/layout/StudioLayout";
import { rawUuid, workspaceRequest } from "../../relay/network";
import { messageOf, post, useWorkspace } from "../workspace/useWorkspace";
import { ChatTranscript } from "./ChatTranscript";
import { AgentModelSelect } from "./AgentModelSelect";
import { AgentSettings } from "./AgentSettings";
import { chatDate, chatTitle, historyGroups, type ChatSummary } from "./history";
import "./agent.css";

export type AgentModel = { id: string; modelId: string; label: string; roles: string[]; enabled: boolean; supportsTools: boolean; apiStyle?: "inherit" | "responses" | "chat_completions"; inputPricePerMillionUsd?: number | null; outputPricePerMillionUsd?: number | null };
export type AgentProvider = { id: string; revision: number; name: string; baseUrl: string; enabled: boolean; local: boolean; models: AgentModel[] };
type AgentMessage = { id: string; role: string; kind: string; content: string; refs: Record<string, unknown>; runId?: string; createdAt?: string };
type AgentRun = { id: string; status: string; error?: string | null; progress?: Record<string, unknown>; modelId?: string; providerId?: string; localModelId?: string; role?: string; cancelRequested?: boolean };
type AgentThread = ChatSummary & { taskId?: string; notebookId?: string; messages?: AgentMessage[]; runs?: AgentRun[]; hasEarlierMessages?: boolean; oldestMessageId?: string | null; automation?: { enabled: boolean; researchGoal: string; scheduleHours: number; nextWakeAt?: string } };
type HistoryResponse = { threads: AgentThread[]; nextOffset: number | null; query: string; ownerScope: string };
type Disclosure = { providerId: string; providerRevision: number; allowPrivate: boolean };
export type AgentPolicy = { remoteDisclosure?: Disclosure | null; remoteDisclosures?: Record<string, Disclosure> | Disclosure[]; autopilot: { enabled: boolean; maxDocumentsPerDay: number; maxHours: number; maxTrainingJobs: number; maxPaidCostUsd: number } };
const defaultPolicy: AgentPolicy = { remoteDisclosure: null, autopilot: { enabled: false, maxDocumentsPerDay: 100, maxHours: 4, maxTrainingJobs: 1, maxPaidCostUsd: 0 } };
const unwrapList = <T,>(value: T[] | { [key: string]: unknown } | null, key: string): T[] => Array.isArray(value) ? value : (value?.[key] as T[] | undefined) ?? [];
const activeStates = ["running", "queued"];
const resumableStates = ["failed", "cancelled", "budget_exhausted", "paused"];
const activeKey = (scope: string) => `studio.agent.activeThread:${scope}`;

export function AgentSidebar() {
  const location = useLocation();
  const [open, setOpen] = useState(false), [expanded, setExpanded] = useState(false), [width, setWidth] = useState(480);
  const [threadId, setThreadId] = useState(""), [providerId, setProviderId] = useState(""), [modelId, setModelId] = useState(""), [role, setRole] = useState("planner");
  const [draft, setDraft] = useState(""), [context, setContext] = useState<Record<string, unknown>>({});
  const [unsentDraftKey, setUnsentDraftKey] = useState("$new");
  const [busy, setBusy] = useState(false), [stopping, setStopping] = useState(false), [error, setError] = useState<string | null>(null), [settings, setSettings] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(true), [historySearch, setHistorySearch] = useState(""), [historyQuery, setHistoryQuery] = useState(""), [historyCursor, setHistoryCursor] = useState<number | null>(null), [loadingHistory, setLoadingHistory] = useState(false);
  const [messageHistory, setMessageHistory] = useState<{ threadId: string; messages: AgentMessage[]; hasEarlier: boolean; oldestId: string | null }>({ threadId: "", messages: [], hasEarlier: false, oldestId: null });
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [historyRows, setHistoryRows] = useState<AgentThread[]>([]), [ownerScope, setOwnerScope] = useState("");
  const [policyDraft, setPolicyDraft] = useState<AgentPolicy>(defaultPolicy), [autopilot, setAutopilot] = useState(false);
  const [researchGoal, setResearchGoal] = useState(""), [scheduleHours, setScheduleHours] = useState(24), [recurring, setRecurring] = useState(false);
  const restoredOwner = useRef("");
  const providersQuery = useWorkspace<AgentProvider[] | { providers: AgentProvider[] }>(open ? "/api/agent-workspace/providers" : null);
  const historyPath = `/api/agent-workspace/threads?q=${encodeURIComponent(historyQuery)}&offset=0&limit=50`;
  const threadsQuery = useWorkspace<AgentThread[] | HistoryResponse>(open ? historyPath : null, open ? 5000 : 0);
  const policyQuery = useWorkspace<AgentPolicy>(open ? "/api/agent-workspace/policies" : null);
  const localModels = useWorkspace<{ id: string; name: string; backend: string; details: Record<string, unknown> }[]>(open ? "/api/learning-workspace/models" : null);
  const background = useWorkspace<{ supported: boolean; installed: boolean; running: boolean }>(open && settings ? "/api/agent-workspace/background" : null);
  const threadQuery = useWorkspace<AgentThread>(open && threadId ? `/api/agent-workspace/threads/${threadId}` : null, open && threadId ? 1800 : 0);
  const providers = unwrapList(providersQuery.data, "providers"), selectedProvider = providers.find((provider) => provider.id === providerId);
  const historyResponse = !Array.isArray(threadsQuery.data) ? threadsQuery.data : null;
  const sameOwner = !ownerScope || !historyResponse?.ownerScope || ownerScope === historyResponse.ownerScope;
  const activeThread = threadQuery.data?.id === threadId && (!restoredOwner.current || !ownerScope || restoredOwner.current === ownerScope) && (!ownerScope || !historyResponse?.ownerScope || ownerScope === historyResponse.ownerScope) ? threadQuery.data : null;
  const activeRun = activeThread?.runs?.find((run) => activeStates.includes(run.status)), lastRun = activeThread?.runs?.[0];
  const currentTitle = chatTitle(activeThread?.title ?? (sameOwner ? historyRows.find((thread) => thread.id === threadId)?.title : undefined));
  const hasModel = providerId === "$runtime" || (providerId.startsWith("local:")
    ? !!localModels.data?.some((model) => `local:${model.id}` === providerId && ["mlx", "transformers"].includes(model.backend) && model.details.state === "ready")
    : !!selectedProvider?.enabled && (!modelId || selectedProvider.models.some((model) => model.enabled && model.modelId === modelId)));
  const groups = historyGroups(sameOwner ? historyRows : [], historyQuery, new Date(), !!historyResponse?.ownerScope);
  const nextOffset = historyCursor;
  const transcript = sameOwner && messageHistory.threadId === threadId ? messageHistory.messages : activeThread?.messages ?? [];
  const endRef = useRef<HTMLDivElement>(null), messagesRef = useRef<HTMLDivElement>(null), composerRef = useRef<HTMLTextAreaElement>(null), searchRef = useRef<HTMLInputElement>(null);
  const historyPageKey = useRef(""), loadedOlderHistory = useRef(false);
  const seenToolEvents = useRef(new Set<string>()), drafts = useRef(new Map<string, string>()), explicitNavigation = useRef(false), defaultModelApplied = useRef(false), shouldStick = useRef(true);
  const asideRef = useRef<HTMLElement>(null), launcherRef = useRef<HTMLButtonElement>(null), settingsRef = useRef<HTMLButtonElement>(null);
  const view = useRef({ historyOpen, settings, threadId, draft, historyQuery, ownerScope, unsentDraftKey }); view.current = { historyOpen, settings, threadId, draft, historyQuery, ownerScope, unsentDraftKey };
  const saveDraft = (value: string) => { setDraft(value); drafts.current.set(threadId || unsentDraftKey, value); };
  const chooseChat = (id: string) => { explicitNavigation.current = true; drafts.current.set(threadId || unsentDraftKey, draft); setDraft(drafts.current.get(id) ?? ""); setThreadId(id); setUnsentDraftKey("$new"); setContext({}); setError(null); setHistoryOpen(expanded); setSettings(false); shouldStick.current = true; };
  const newChat = () => { explicitNavigation.current = true; drafts.current.set(threadId || unsentDraftKey, draft); setThreadId(""); setUnsentDraftKey("$new"); setContext({}); setDraft(drafts.current.get("$new") ?? ""); setError(null); setHistoryOpen(expanded); setSettings(false); shouldStick.current = true; composerRef.current?.focus(); };
  useEffect(() => { const timer = window.setTimeout(() => { setHistoryQuery(historySearch.trim()); }, 200); return () => window.clearTimeout(timer); }, [historySearch]);
  useEffect(() => {
    const response = threadsQuery.data;
    if (!response || (!Array.isArray(response) && response.query !== historyQuery)) return;
    const rows = Array.isArray(response) ? response : response.threads;
    if (!Array.isArray(response) && response.ownerScope) setOwnerScope(response.ownerScope);
    const key = `${Array.isArray(response) ? "legacy" : response.ownerScope}:${historyQuery}`;
    const same = historyPageKey.current === key; historyPageKey.current = key;
    if (!same) loadedOlderHistory.current = false;
    setHistoryRows((previous) => same ? [...new Map([...rows, ...previous.filter((row) => !rows.some((newRow) => newRow.id === row.id))].map((row) => [row.id, row])).values()] : rows);
    if (!loadedOlderHistory.current) setHistoryCursor(Array.isArray(response) ? null : response.nextOffset);
  }, [threadsQuery.data, historyQuery]);
  useEffect(() => {
    if (!ownerScope || restoredOwner.current === ownerScope) return;
    const changedOwner = !!restoredOwner.current && restoredOwner.current !== ownerScope;
    restoredOwner.current = ownerScope;
    if (changedOwner) { drafts.current.clear(); setDraft(""); setThreadId(""); setUnsentDraftKey("$new"); setContext({}); setHistoryOpen(true); setProviderId(""); setModelId(""); defaultModelApplied.current = false; setMessageHistory({ threadId: "", messages: [], hasEarlier: false, oldestId: null }); explicitNavigation.current = false; }
    if (explicitNavigation.current) return;
    try { const saved = localStorage.getItem(activeKey(ownerScope)); if (saved) { setThreadId(saved); setHistoryOpen(false); shouldStick.current = true; } } catch { /* Storage may be disabled. */ }
  }, [ownerScope]);
  useEffect(() => {
    if (!ownerScope || restoredOwner.current !== ownerScope) return;
    // A restored ID is a UI preference only; the server still authorizes every read.
    if (!threadId && !explicitNavigation.current) return;
    if (threadId && !activeThread && !historyRows.some((thread) => thread.id === threadId)) return;
    try { if (threadId) localStorage.setItem(activeKey(ownerScope), threadId); else localStorage.removeItem(activeKey(ownerScope)); } catch { /* Storage may be disabled. */ }
  }, [ownerScope, threadId, activeThread?.id, historyRows]);
  useEffect(() => {
    if (!activeThread) return;
    setMessageHistory((previous) => {
      const incoming = activeThread.messages ?? [];
      const same = previous.threadId === activeThread.id;
      const previousIds = new Set(previous.messages.map((message) => message.id));
      // Background work can advance beyond the latest-page window while chat is closed.
      // Without overlap, keep one coherent server page so its earlier cursor fills the gap.
      const disjoint = same && previous.messages.length > 0 && incoming.length > 0 && !incoming.some((message) => previousIds.has(message.id));
      const keepPrevious = same && !disjoint;
      const merged = [...new Map([...(keepPrevious ? previous.messages : []), ...incoming].map((message) => [message.id, message])).values()];
      return { threadId: activeThread.id, messages: merged, hasEarlier: keepPrevious && previous.messages.length ? previous.hasEarlier : !!activeThread.hasEarlierMessages, oldestId: keepPrevious && previous.oldestId ? previous.oldestId : activeThread.oldestMessageId ?? merged[0]?.id ?? null };
    });
  }, [activeThread?.id, activeThread?.messages, activeThread?.hasEarlierMessages, activeThread?.oldestMessageId]);
  useEffect(() => {
    if (!threadId || threadQuery.errorStatus !== 404) return;
    if (ownerScope) { try { localStorage.removeItem(activeKey(ownerScope)); } catch { /* Storage may be disabled. */ } }
    drafts.current.delete(threadId); setThreadId(""); setUnsentDraftKey("$new"); setContext({}); setDraft(""); setMessageHistory({ threadId: "", messages: [], hasEarlier: false, oldestId: null }); setHistoryOpen(true); setError("That chat is no longer available. Choose another chat."); explicitNavigation.current = true;
  }, [threadId, threadQuery.errorStatus, ownerScope]);
  useEffect(() => {
    const compact = () => { if (window.innerWidth <= 1000 && expanded) { setExpanded(false); setHistoryOpen(false); } };
    window.addEventListener("resize", compact); compact(); return () => window.removeEventListener("resize", compact);
  }, [expanded]);
  useEffect(() => {
    if (threadId || defaultModelApplied.current || !providersQuery.data) return;
    const provider = providers.find((item) => item.enabled && item.models.some((model) => model.enabled && model.supportsTools));
    const model = provider?.models.find((item) => item.enabled && item.supportsTools && item.roles.includes("planner")) ?? provider?.models.find((item) => item.enabled && item.supportsTools);
    if (provider && model) { setProviderId(provider.id); setModelId(model.modelId); defaultModelApplied.current = true; }
  }, [providersQuery.data, threadId]);
  useEffect(() => {
    const recent = activeThread?.runs?.[0]; if (!recent) return;
    setProviderId(recent.localModelId ? `local:${recent.localModelId}` : recent.providerId ?? "$runtime");
    setModelId(recent.localModelId ? "" : recent.modelId ?? "");
    if (recent.role) setRole(recent.role);
    defaultModelApplied.current = true;
  }, [activeThread?.id, activeThread?.runs?.[0]?.id]);
  useEffect(() => { if (policyQuery.data) setPolicyDraft(policyQuery.data); }, [policyQuery.data]);
  useEffect(() => { const automation = activeThread?.automation; setResearchGoal(automation?.researchGoal ?? ""); setRecurring(automation?.enabled ?? false); setScheduleHours(automation?.scheduleHours ?? 24); }, [activeThread?.id, activeThread?.automation?.nextWakeAt]);
  useEffect(() => { const refresh = () => { void providersQuery.refresh(); }; window.addEventListener("studio-provider-models-updated", refresh); return () => window.removeEventListener("studio-provider-models-updated", refresh); }, [providersQuery.refresh]);
  useEffect(() => {
    if (!open) return;
    const refresh = () => { void threadsQuery.refresh(); if (threadId) void threadQuery.refresh(); };
    window.addEventListener("focus", refresh); return () => window.removeEventListener("focus", refresh);
  }, [open, threadId, threadsQuery.refresh, threadQuery.refresh]);
  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail ?? {};
      explicitNavigation.current = true; setOpen(true); setSettings(false); shouldStick.current = true;
      drafts.current.set(view.current.threadId || view.current.unsentDraftKey, view.current.draft);
      if (typeof detail.threadId === "string") { setThreadId(detail.threadId); setUnsentDraftKey("$new"); setDraft(drafts.current.get(detail.threadId) ?? ""); setContext({}); setHistoryOpen(false); }
      else if (detail.notebookId || detail.taskId || detail.sourceId || detail.memoryId) {
        const key = `$context:${JSON.stringify([detail.notebookId ?? null, detail.taskId ?? null, detail.sourceId ?? null, detail.memoryId ?? null])}`;
        setContext(detail); setThreadId(""); setUnsentDraftKey(key); setHistoryOpen(false);
        setDraft(drafts.current.get(key) ?? (typeof detail.message === "string" ? detail.message : ""));
      }
      else { setHistoryOpen(false); if (typeof detail.message === "string") setDraft(detail.message); }
    };
    const clear = () => { drafts.current.clear(); setThreadId(""); setUnsentDraftKey("$new"); setDraft(""); setHistoryRows([]); setHistorySearch(""); setHistoryQuery(""); setHistoryCursor(null); historyPageKey.current = ""; setMessageHistory({ threadId: "", messages: [], hasEarlier: false, oldestId: null }); setOwnerScope(""); setContext({}); setOpen(false); restoredOwner.current = ""; explicitNavigation.current = false; defaultModelApplied.current = false; setProviderId(""); setModelId(""); };
    window.addEventListener("studio-agent-open", listener); window.addEventListener("studio-auth-cleared", clear);
    return () => { window.removeEventListener("studio-agent-open", listener); window.removeEventListener("studio-auth-cleared", clear); };
  }, []);
  useEffect(() => {
    document.documentElement.style.setProperty("--agent-panel-width", `${open && !expanded ? width : 0}px`);
    document.documentElement.classList.toggle("has-agent-panel", open); document.documentElement.classList.toggle("has-expanded-chat", open && expanded);
    return () => { document.documentElement.classList.remove("has-agent-panel", "has-expanded-chat"); document.documentElement.style.removeProperty("--agent-panel-width"); };
  }, [open, expanded, width]);
  useEffect(() => { if (open && (!historyOpen || expanded) && shouldStick.current) endRef.current?.scrollIntoView({ block: "nearest" }); }, [open, historyOpen, expanded, transcript.length]);
  useEffect(() => { if (open && historyOpen) searchRef.current?.focus(); }, [open, historyOpen]);
  useEffect(() => { if (open && !historyOpen) composerRef.current?.focus(); }, [open, historyOpen, threadId]);
  useEffect(() => { const results = activeThread?.messages?.filter((item) => item.kind === "tool_result" && !seenToolEvents.current.has(item.id)) ?? []; if (!results.length) return; results.forEach((item) => seenToolEvents.current.add(item.id)); window.dispatchEvent(new Event("studio-workspace-updated")); }, [activeThread?.messages]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null, previousOverflow = document.body.style.overflow;
    if (window.matchMedia("(max-width: 1000px)").matches) document.body.style.overflow = "hidden";
    const listener = (event: KeyboardEvent) => {
      // Radix dialogs and listboxes own their keyboard/focus lifecycle, including portals.
      if (event.defaultPrevented || view.current.settings || (event.target instanceof Element && event.target.closest('[role="listbox"], [role="dialog"], [data-slot="select-content"]'))) return;
      if (event.key === "Escape") { if (view.current.settings) setSettings(false); else if (view.current.historyOpen && view.current.threadId) setHistoryOpen(false); else { setOpen(false); launcherRef.current?.focus(); } }
      if (event.key !== "Tab" || !window.matchMedia("(max-width: 1000px)").matches) return;
      const controls = [...(asideRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, textarea, select, summary') ?? [])].filter((node) => node.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", listener); return () => { document.removeEventListener("keydown", listener); document.body.style.overflow = previousOverflow; previous?.isConnected && previous.focus(); };
  }, [open]);
  const providerPayload = () => ({ providerId: providerId && providerId !== "$runtime" && !providerId.startsWith("local:") ? providerId : undefined, localModelId: providerId.startsWith("local:") ? providerId.slice(6) : undefined, modelId: modelId || undefined, role });
  const send = async (event: FormEvent) => {
    event.preventDefault(); if (busy || activeRun || !draft.trim() || !hasModel) return;
    setBusy(true); setError(null);
    try {
      let id = threadId;
      if (!id) { const routeTask = location.pathname.match(/^\/tasks\/([^/]+)/)?.[1]; const thread = await post<AgentThread>("/api/agent-workspace/threads", { title: draft.replace(/\s+/g, " ").slice(0, 100), taskId: context.taskId ?? (routeTask ? rawUuid(decodeURIComponent(routeTask)) : undefined), notebookId: context.notebookId }); id = thread.id; setThreadId(id); explicitNavigation.current = true; await threadsQuery.refresh(); }
      await post(`/api/agent-workspace/threads/${id}/runs`, { message: draft, ...providerPayload(), autopilot });
      drafts.current.delete(threadId || unsentDraftKey); drafts.current.delete(id); setUnsentDraftKey("$new"); setDraft(""); shouldStick.current = true; await threadQuery.refresh(); await threadsQuery.refresh();
    } catch (e) { setError(messageOf(e)); } finally { setBusy(false); }
  };
  const stop = async () => { if (!activeRun || stopping) return; setStopping(true); try { await post(`/api/agent-workspace/runs/${activeRun.id}/cancel`); await threadQuery.refresh(); } catch (e) { setError(messageOf(e)); } finally { setStopping(false); } };
  const savePolicy = async () => { setBusy(true); setError(null); try { await workspaceRequest("/api/agent-workspace/policies", { method: "PUT", body: JSON.stringify(policyDraft) }); await policyQuery.refresh(); } catch (e) { setError(messageOf(e)); } finally { setBusy(false); } };
  const saveSchedule = async () => { if (!threadId) return; setBusy(true); setError(null); try { await workspaceRequest(`/api/agent-workspace/threads/${threadId}/automation`, { method: "PUT", body: JSON.stringify({ enabled: recurring, researchGoal, scheduleHours, ...providerPayload() }) }); await threadQuery.refresh(); } catch (e) { setError(messageOf(e)); } finally { setBusy(false); } };
  const selectedDisclosure = (() => { const all = policyDraft.remoteDisclosures; const value = Array.isArray(all) ? all.find((item) => item.providerId === providerId) : all?.[providerId]; return value ?? (policyDraft.remoteDisclosure?.providerId === providerId ? policyDraft.remoteDisclosure : null); })();
  const toggleDisclosure = (allowPrivate: boolean) => { if (!selectedProvider) return; const disclosure = { providerId, providerRevision: selectedProvider.revision, allowPrivate }; const previous = policyDraft.remoteDisclosures; const disclosures = Array.isArray(previous) ? Object.fromEntries(previous.map((item) => [item.providerId, item])) : previous ?? {}; setPolicyDraft({ ...policyDraft, remoteDisclosure: disclosure, remoteDisclosures: { ...disclosures, [providerId]: disclosure } }); };
  const loadOlderChats = async () => {
    if (nextOffset === null || loadingHistory) return;
    const query = historyQuery, scope = ownerScope; setLoadingHistory(true);
    try { const response = await workspaceRequest<HistoryResponse>(`/api/agent-workspace/threads?q=${encodeURIComponent(query)}&offset=${nextOffset}&limit=50`); if (view.current.historyQuery !== query || view.current.ownerScope !== scope || response.ownerScope !== scope) return; loadedOlderHistory.current = true; setHistoryRows((previous) => [...new Map([...previous, ...response.threads].map((thread) => [thread.id, thread])).values()]); setHistoryCursor(response.nextOffset); } catch (e) { setError(messageOf(e)); } finally { setLoadingHistory(false); }
  };
  const loadEarlier = async () => {
    const id = threadId, cursor = messageHistory.threadId === id ? messageHistory.oldestId : activeThread?.oldestMessageId;
    if (!id || !cursor || loadingEarlier) return;
    setLoadingEarlier(true);
    try { const page = await workspaceRequest<AgentThread>(`/api/agent-workspace/threads/${id}?before=${encodeURIComponent(cursor)}&limit=500`); if (view.current.threadId !== id) return; shouldStick.current = false; const element = messagesRef.current, oldHeight = element?.scrollHeight ?? 0; setMessageHistory((previous) => ({ threadId: id, messages: [...new Map([...(page.messages ?? []), ...(previous.threadId === id ? previous.messages : [])].map((message) => [message.id, message])).values()], hasEarlier: !!page.hasEarlierMessages, oldestId: page.oldestMessageId ?? null })); window.requestAnimationFrame(() => { if (element) element.scrollTop += element.scrollHeight - oldHeight; }); } catch (e) { setError(messageOf(e)); } finally { setLoadingEarlier(false); }
  };
  const historyPane = <section className="cs-chat-history" aria-label="Chat history"><div className="cs-chat-history-heading"><h2>Chats</h2><Button variant="ghost" size="icon" aria-label="Refresh chat history" onClick={() => void threadsQuery.refresh()}><RefreshCw size={15} /></Button></div><Input ref={searchRef} className="cs-chat-history-search" type="search" aria-label="Search chats" value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="Search your chats" />{threadsQuery.loading && !historyRows.length ? <p role="status">Loading chats…</p> : !groups.length ? <div className="cs-chat-history-empty"><strong>{historyQuery ? "No matching chats" : "Your chats will appear here"}</strong><p>{historyQuery ? "Try another word or phrase." : "Start a chat to save your conversation."}</p></div> : groups.map((group) => <section className="cs-chat-history-group" key={group.label}><h3>{group.label}</h3>{group.threads.map((thread) => <Button variant="ghost" className={`cs-chat-history-row${thread.id === threadId ? " is-selected" : ""}`} key={thread.id} aria-label={`Open chat: ${chatTitle(thread.title)}`} aria-current={thread.id === threadId ? "page" : undefined} onClick={() => chooseChat(thread.id)}><span className="cs-chat-history-title">{chatTitle(thread.title)}</span>{thread.lastMessagePreview && <span className="cs-chat-history-preview">{thread.lastMessagePreview}</span>}<span className="cs-chat-history-meta"><span>{chatDate(thread)}{thread.messageCount !== undefined ? ` · ${thread.messageCount} messages` : ""}</span>{thread.lastRunStatus && <span className={activeStates.includes(thread.lastRunStatus) ? "is-active" : ""}>{activeStates.includes(thread.lastRunStatus) ? "Running" : resumableStates.includes(thread.lastRunStatus) ? "Paused" : ""}</span>}</span></Button>)}</section>)}{nextOffset !== null && nextOffset !== undefined && <Button variant="ghost" disabled={loadingHistory} onClick={() => void loadOlderChats()}>{loadingHistory ? "Loading…" : "Load older chats"}</Button>}</section>;
  return <TooltipProvider delayDuration={350}>
    <Button variant="outline" ref={launcherRef} type="button" className={`cs-agent-launcher${open ? " is-open" : ""}`} aria-label={open ? "Close research agent" : "Open research agent"} aria-expanded={open} aria-controls="research-agent" onClick={() => setOpen(!open)}><StudioIcon name="models" /><span>Agent</span>{activeRun && <span className="cs-live-dot" />}</Button>
    {open && <button className="cs-agent-backdrop" aria-label="Close research agent" onClick={() => setOpen(false)} />}
    {open && <aside ref={asideRef} id="research-agent" className={`cs-agent-panel cs-chat-panel${expanded ? " is-expanded" : ""}`} aria-label="Research agent" style={{ "--panel-width": `${width}px` } as CSSProperties}>
      <header className="cs-chat-toolbar"><span className="cs-chat-toolbar-brand">Agent</span><div>
        <Button type="button" variant="ghost" size="sm" className="cs-chat-toolbar-button" onClick={newChat}><Plus size={15} />New chat</Button>
        <Button type="button" variant="ghost" size="sm" className={`cs-chat-toolbar-button${historyOpen ? " is-selected" : ""}`} aria-expanded={historyOpen} onClick={() => { setHistoryOpen(!historyOpen); setSettings(false); }}><History size={15} />History</Button>
        <Tooltip><TooltipTrigger asChild><Button type="button" variant="ghost" size="icon" className="cs-chat-icon-button cs-chat-expand-button" aria-label={expanded ? "Collapse chat" : "Expand chat"} onClick={() => { setExpanded(!expanded); setHistoryOpen(!expanded); }}>{expanded ? <ArrowDownLeft size={16} /> : <Expand size={16} />}</Button></TooltipTrigger><TooltipContent>{expanded ? "Collapse chat" : "Expand chat"}</TooltipContent></Tooltip>
        <Tooltip><TooltipTrigger asChild><Button ref={settingsRef} type="button" variant="ghost" size="icon" className="cs-chat-icon-button" aria-label="Agent settings" aria-haspopup="dialog" aria-expanded={settings} onClick={() => setSettings(true)}><Settings2 size={16} /></Button></TooltipTrigger><TooltipContent>Chat settings</TooltipContent></Tooltip>
        <Tooltip><TooltipTrigger asChild><Button type="button" variant="ghost" size="icon" className="cs-chat-icon-button" aria-label="Close agent" onClick={() => setOpen(false)}><X size={17} /></Button></TooltipTrigger><TooltipContent>Close chat panel</TooltipContent></Tooltip>
      </div></header>
      <AgentSettings open={settings} onOpenChange={setSettings} restoreFocus={() => settingsRef.current?.focus()} busy={busy} role={role} onRoleChange={setRole} width={width} onWidthChange={setWidth} policy={policyDraft} onPolicyChange={setPolicyDraft} provider={selectedProvider} disclosureChecked={!!selectedDisclosure?.allowPrivate && selectedDisclosure.providerRevision === selectedProvider?.revision} onDisclosureChange={toggleDisclosure} onSave={() => void savePolicy()} threadId={threadId} recurring={recurring} onRecurringChange={setRecurring} researchGoal={researchGoal} onResearchGoalChange={setResearchGoal} scheduleHours={scheduleHours} onScheduleHoursChange={setScheduleHours} nextWakeAt={activeThread?.automation?.nextWakeAt} onSaveSchedule={() => void saveSchedule()} background={background.data} onBackgroundChange={() => { setBusy(true); void post("/api/agent-workspace/background", { action: background.data?.installed ? "uninstall" : "install" }).then(background.refresh).catch((e) => setError(messageOf(e))).finally(() => setBusy(false)); }} />
      {(error || providersQuery.error || threadsQuery.error || threadQuery.error) && <p className="cs-workspace-error" role="alert">{error ?? providersQuery.error ?? threadsQuery.error ?? threadQuery.error}</p>}
      <div className={`cs-chat-layout${expanded && historyOpen ? " has-history-rail" : ""}`}>
        {historyOpen && historyPane}
        {(!historyOpen || expanded) && <section className="cs-chat-conversation" aria-label="Current chat"><header className="cs-chat-current"><h2 title={currentTitle}>{currentTitle}</h2><div className="cs-chat-model-control"><AgentModelSelect providers={providers} localModels={localModels.data ?? []} providerId={providerId} modelId={modelId} onChange={(provider, model) => { setProviderId(provider); setModelId(model); defaultModelApplied.current = true; }} /></div></header>
          <div ref={messagesRef} className="cs-chat-transcript" role="log" aria-label="Agent conversation messages" aria-live="polite" onScroll={() => { const element = messagesRef.current; if (element) shouldStick.current = element.scrollHeight - element.scrollTop - element.clientHeight < 100; }}>
            {threadQuery.loading && threadId && !activeThread ? <p className="cs-chat-loading" role="status">Opening chat…</p> : !transcript.length ? <div className="cs-chat-welcome"><span aria-hidden="true">✦</span><h3>What would you like to explore?</h3><p>Work with your sources, notes, and local models.</p><div>{["Find papers for my research", "Review my latest training run"].map((prompt) => <Button key={prompt} type="button" variant="outline" onClick={() => saveDraft(prompt)}>{prompt} <span aria-hidden="true">↗</span></Button>)}</div></div> : <>{(messageHistory.threadId === threadId ? messageHistory.hasEarlier : activeThread?.hasEarlierMessages) && <div className="cs-chat-earlier-note"><Button type="button" variant="outline" size="sm" disabled={loadingEarlier} onClick={() => void loadEarlier()}>{loadingEarlier ? "Loading…" : "Load earlier messages"}</Button></div>}<ChatTranscript messages={transcript} activeRunId={activeRun?.id} /></>}
            {lastRun && (activeRun || resumableStates.includes(lastRun.status) || lastRun.error) && <div className="cs-chat-run-state" role="status"><span className={activeRun ? "cs-live-dot" : ""} /><span>{activeRun ? activeRun.progress?.waitingForJob ? "Waiting for a compute job…" : "Agent is working…" : lastRun.status.replaceAll("_", " ")}</span>{!activeRun && resumableStates.includes(lastRun.status) && <Button variant="ghost" onClick={() => void post(`/api/agent-workspace/runs/${lastRun.id}/resume`).then(threadQuery.refresh).catch((e) => setError(messageOf(e)))}>Resume</Button>}{lastRun.error && <p>{lastRun.error}</p>}</div>}
            {lastRun?.progress && <div className="cs-chat-run-details"><TechnicalDetails label="Run details" value={lastRun.progress} /></div>}<div ref={endRef} />
          </div>
          <form className="cs-chat-composer" onSubmit={(event) => void send(event)}><div className="cs-chat-input-box"><Textarea ref={composerRef} aria-label="Message research agent" placeholder={activeRun ? "Write your next message…" : "Message Agent…"} rows={2} maxLength={32000} value={draft} onChange={(event) => saveDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!activeRun) event.currentTarget.form?.requestSubmit(); } }} /><div className="cs-chat-composer-controls"><Select value={autopilot ? "autopilot" : "chat"} onValueChange={(value) => setAutopilot(value === "autopilot")}><SelectTrigger aria-label="Chat mode" size="sm" className="cs-chat-mode-trigger"><SelectValue /></SelectTrigger><SelectContent position="popper" align="start"><SelectItem value="chat">Chat</SelectItem><SelectItem value="autopilot" disabled={!policyQuery.data?.autopilot.enabled}>Autopilot</SelectItem></SelectContent></Select><span>{hasModel ? "Enter to send · Shift Enter for a new line" : "Choose a model to begin"}</span>{activeRun ? <Button type="button" className="cs-chat-stop" onClick={() => void stop()} disabled={stopping || activeRun.cancelRequested}><Square size={12} fill="currentColor" />{stopping || activeRun.cancelRequested ? "Stopping…" : "Stop"}</Button> : <Button type="submit" className="cs-chat-send" disabled={busy || !draft.trim() || !hasModel}><ArrowUp size={17} />{busy ? "Sending…" : "Send"}</Button>}</div></div><p className="cs-chat-private-hint">Private chat · activity and sources are saved</p></form>
        </section>}
      </div>
    </aside>}
  </TooltipProvider>;
}
