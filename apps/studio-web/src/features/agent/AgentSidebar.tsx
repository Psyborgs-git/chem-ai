import { lazy, Suspense, useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { useLocation } from "react-router";
import { Button } from "../../components/atoms/Button";
import { StudioIcon, StructuredData } from "../../components/layout/StudioLayout";
import { rawUuid, workspaceRequest } from "../../relay/network";
import { messageOf, post, useWorkspace } from "../workspace/useWorkspace";
import "./agent.css";

const MarkdownPreview = lazy(() => import("../notebooks/MarkdownPreview").then((module) => ({ default: module.MarkdownPreview })));

export type AgentModel = { id: string; modelId: string; label: string; roles: string[]; enabled: boolean; supportsTools: boolean; apiStyle?: "inherit" | "responses" | "chat_completions"; inputPricePerMillionUsd?: number | null; outputPricePerMillionUsd?: number | null };
export type AgentProvider = { id: string; revision: number; name: string; baseUrl: string; enabled: boolean; local: boolean; models: AgentModel[] };
type AgentMessage = { id: string; role: string; kind: string; content: string; refs: Record<string, unknown> };
type AgentRun = { id: string; status: string; error?: string | null; progress?: Record<string, unknown>; modelId?: string; providerId?: string };
type AgentThread = { id: string; title: string; taskId?: string; notebookId?: string; messages?: AgentMessage[]; runs?: AgentRun[]; automation?: { enabled: boolean; researchGoal: string; scheduleHours: number; nextWakeAt?: string } };
type Disclosure = { providerId: string; providerRevision: number; allowPrivate: boolean };
type AgentPolicy = { remoteDisclosure?: Disclosure | null; remoteDisclosures?: Record<string, Disclosure> | Disclosure[]; autopilot: { enabled: boolean; maxDocumentsPerDay: number; maxHours: number; maxTrainingJobs: number; maxPaidCostUsd: number } };
const defaultPolicy: AgentPolicy = { remoteDisclosure: null, autopilot: { enabled: false, maxDocumentsPerDay: 100, maxHours: 4, maxTrainingJobs: 1, maxPaidCostUsd: 0 } };
const unwrapList = <T,>(value: T[] | { [key: string]: unknown } | null, key: string): T[] => Array.isArray(value) ? value : (value?.[key] as T[] | undefined) ?? [];

export function AgentSidebar() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [width, setWidth] = useState(420);
  const [threadId, setThreadId] = useState("");
  const [providerId, setProviderId] = useState("");
  const [modelId, setModelId] = useState("");
  const [role, setRole] = useState("planner");
  const [draft, setDraft] = useState("");
  const [context, setContext] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState(false);
  const [policyDraft, setPolicyDraft] = useState<AgentPolicy>(defaultPolicy);
  const [autopilot, setAutopilot] = useState(false);
  const [researchGoal, setResearchGoal] = useState("");
  const [scheduleHours, setScheduleHours] = useState(24);
  const [recurring, setRecurring] = useState(false);
  const providersQuery = useWorkspace<AgentProvider[] | { providers: AgentProvider[] }>(open ? "/api/agent-workspace/providers" : null);
  const threadsQuery = useWorkspace<AgentThread[] | { threads: AgentThread[] }>(open ? "/api/agent-workspace/threads" : null);
  const policyQuery = useWorkspace<AgentPolicy>(open ? "/api/agent-workspace/policies" : null);
  const localModels = useWorkspace<{ id: string; name: string; backend: string; details: Record<string, unknown> }[]>(open ? "/api/learning-workspace/models" : null);
  const background = useWorkspace<{ supported: boolean; installed: boolean; running: boolean }>(open && settings ? "/api/agent-workspace/background" : null);
  const threadQuery = useWorkspace<AgentThread>(open && threadId ? `/api/agent-workspace/threads/${threadId}` : null, open && threadId ? 1800 : 0);
  const providers = unwrapList(providersQuery.data, "providers");
  const threads = unwrapList(threadsQuery.data, "threads");
  const selectedProvider = providers.find((provider) => provider.id === providerId);
  const models = selectedProvider?.models.filter((model) => model.enabled) ?? [];
  const activeRun = threadQuery.data?.runs?.find((run) => ["running", "queued"].includes(run.status));
  const lastRun = threadQuery.data?.runs?.[0];
  const endRef = useRef<HTMLDivElement>(null);
  const seenToolEvents = useRef(new Set<string>());
  const asideRef = useRef<HTMLElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (policyQuery.data) setPolicyDraft(policyQuery.data); }, [policyQuery.data]);
  useEffect(() => {
    const automation = threadQuery.data?.automation;
    setResearchGoal(automation?.researchGoal ?? ""); setRecurring(automation?.enabled ?? false); setScheduleHours(automation?.scheduleHours ?? 24);
  }, [threadQuery.data?.id, threadQuery.data?.automation?.nextWakeAt]);
  useEffect(() => {
    const refresh = () => { void providersQuery.refresh(); };
    window.addEventListener("studio-provider-models-updated", refresh);
    return () => window.removeEventListener("studio-provider-models-updated", refresh);
  }, [providersQuery.refresh]);
  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail ?? {};
      setOpen(true);
      if (typeof detail.message === "string") setDraft(detail.message);
      if (detail.notebookId || detail.taskId || detail.sourceId || detail.memoryId) { setContext(detail); setThreadId(""); }
    };
    window.addEventListener("studio-agent-open", listener);
    return () => window.removeEventListener("studio-agent-open", listener);
  }, []);
  useEffect(() => {
    document.documentElement.style.setProperty("--agent-panel-width", `${open ? width : 0}px`);
    document.documentElement.classList.toggle("has-agent-panel", open);
    return () => { document.documentElement.classList.remove("has-agent-panel"); document.documentElement.style.removeProperty("--agent-panel-width"); };
  }, [open, width]);
  useEffect(() => { if (open) endRef.current?.scrollIntoView({ block: "nearest" }); }, [open, threadQuery.data?.messages?.length]);
  useEffect(() => {
    const results = threadQuery.data?.messages?.filter((item) => item.kind === "tool_result" && !seenToolEvents.current.has(item.id)) ?? [];
    if (!results.length) return;
    results.forEach((item) => seenToolEvents.current.add(item.id));
    window.dispatchEvent(new Event("studio-workspace-updated"));
  }, [threadQuery.data?.messages]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    if (window.matchMedia("(max-width: 1000px)").matches) document.body.style.overflow = "hidden";
    asideRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); launcherRef.current?.focus(); }
      if (event.key !== "Tab" || !window.matchMedia("(max-width: 1000px)").matches) return;
      const controls = [...(asideRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, textarea, select, summary') ?? [])].filter((node) => node.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", listener);
    return () => { document.removeEventListener("keydown", listener); document.body.style.overflow = previousOverflow; previous?.isConnected && previous.focus(); };
  }, [open]);
  const send = async (event: FormEvent) => {
    event.preventDefault(); if (busy || activeRun || !draft.trim()) return;
    setBusy(true); setError(null);
    try {
      let id = threadId;
      if (!id) {
        const routeTask = location.pathname.match(/^\/tasks\/([^/]+)/)?.[1];
        const thread = await post<AgentThread>("/api/agent-workspace/threads", { title: draft.slice(0, 100), taskId: context.taskId ?? (routeTask ? rawUuid(decodeURIComponent(routeTask)) : undefined), notebookId: context.notebookId });
        id = thread.id; setThreadId(id); await threadsQuery.refresh();
      }
      await post(`/api/agent-workspace/threads/${id}/runs`, { message: draft, providerId: providerId && !providerId.startsWith("local:") ? providerId : undefined, localModelId: providerId.startsWith("local:") ? providerId.slice(6) : undefined, modelId: modelId || undefined, role, autopilot });
      setDraft(""); await threadQuery.refresh();
    } catch (e) { setError(messageOf(e)); } finally { setBusy(false); }
  };
  const savePolicy = async () => {
    setBusy(true); setError(null);
    try { await workspaceRequest("/api/agent-workspace/policies", { method: "PUT", body: JSON.stringify(policyDraft) }); await policyQuery.refresh(); }
    catch (e) { setError(messageOf(e)); } finally { setBusy(false); }
  };
  const saveSchedule = async () => {
    if (!threadId) return;
    setBusy(true); setError(null);
    try { await workspaceRequest(`/api/agent-workspace/threads/${threadId}/automation`, { method: "PUT", body: JSON.stringify({ enabled: recurring, researchGoal, scheduleHours, providerId: providerId && !providerId.startsWith("local:") ? providerId : undefined, localModelId: providerId.startsWith("local:") ? providerId.slice(6) : undefined, modelId: modelId || undefined, role }) }); await threadQuery.refresh(); }
    catch (e) { setError(messageOf(e)); } finally { setBusy(false); }
  };
  const selectedDisclosure = (() => { const all = policyDraft.remoteDisclosures; const value = Array.isArray(all) ? all.find((item) => item.providerId === providerId) : all?.[providerId]; return value ?? (policyDraft.remoteDisclosure?.providerId === providerId ? policyDraft.remoteDisclosure : null); })();
  const toggleDisclosure = (allowPrivate: boolean) => {
    if (!selectedProvider) return;
    const disclosure = { providerId, providerRevision: selectedProvider.revision, allowPrivate };
    const previous = policyDraft.remoteDisclosures;
    const disclosures = Array.isArray(previous) ? Object.fromEntries(previous.map((item) => [item.providerId, item])) : previous ?? {};
    setPolicyDraft({ ...policyDraft, remoteDisclosure: disclosure, remoteDisclosures: { ...disclosures, [providerId]: disclosure } });
  };
  return <>
    <button ref={launcherRef} type="button" className={`cs-agent-launcher${open ? " is-open" : ""}`} aria-label={open ? "Close research agent" : "Open research agent"} aria-expanded={open} aria-controls="research-agent" onClick={() => setOpen(!open)}><StudioIcon name="models" /><span>Agent</span>{activeRun && <span className="cs-live-dot" />}</button>
    {open && <button className="cs-agent-backdrop" aria-label="Close research agent" onClick={() => setOpen(false)} />}
    {open && <aside ref={asideRef} id="research-agent" className="cs-agent-panel" aria-label="Research agent" style={{ "--panel-width": `${width}px` } as CSSProperties}>
      <header className="cs-agent-header"><div><span className="cs-kicker">Your research partner</span><h2>Studio agent</h2></div><Button variant="ghost" onClick={() => setSettings(!settings)} aria-expanded={settings}>Settings</Button><Button variant="ghost" aria-label="Close agent" onClick={() => setOpen(false)}>×</Button></header>
      <div className="cs-agent-selection"><select className="cs-input" aria-label="Agent conversation" value={threadId} onChange={(event) => { setThreadId(event.target.value); setContext({}); setError(null); }}><option value="">New conversation</option>{threads.map((thread) => <option value={thread.id} key={thread.id}>{thread.title}</option>)}</select><div className="cs-agent-models"><select className="cs-input" aria-label="Agent provider" value={providerId} onChange={(event) => { setProviderId(event.target.value); setModelId(""); }}><option value="">Local runtime</option>{localModels.data?.filter((model) => ["mlx", "transformers"].includes(model.backend) && model.details.state !== "downloading").map((model) => <option key={model.id} value={`local:${model.id}`}>Private · {model.name}</option>)}{providers.map((provider) => <option disabled={!provider.enabled} key={provider.id} value={provider.id}>{provider.name}{!provider.enabled ? " (disabled)" : ""}</option>)}</select><select className="cs-input" aria-label="Agent model" value={modelId} onChange={(event) => setModelId(event.target.value)} disabled={!selectedProvider}><option value="">{selectedProvider ? "Role default" : "Private local model"}</option>{models.map((model) => <option key={model.id} value={model.modelId}>{model.label}</option>)}</select></div><label className="cs-agent-role">Role<select className="cs-input" value={role} onChange={(event) => setRole(event.target.value)}>{["planner", "researcher", "extractor", "reviewer"].map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div>
      {settings && <section className="cs-agent-settings" aria-label="Agent settings"><h3>Autopilot and privacy</h3><label><input type="checkbox" checked={policyDraft.autopilot.enabled} onChange={(event) => setPolicyDraft({ ...policyDraft, autopilot: { ...policyDraft.autopilot, enabled: event.target.checked } })} /> Enable research and training autopilot</label><div className="cs-agent-budget">{([['maxHours', 'Compute hours/day', 24], ['maxDocumentsPerDay', 'Documents/day', 10000], ['maxPaidCostUsd', 'API budget USD/day', 10000]] as const).map(([key, label, max]) => <label className="cs-field" key={key}><span className="cs-field__label">{label}</span><input className="cs-input" type="number" min={key === "maxPaidCostUsd" ? 0 : 1} max={max} value={policyDraft.autopilot[key]} onChange={(event) => setPolicyDraft({ ...policyDraft, autopilot: { ...policyDraft.autopilot, [key]: Number(event.target.value) } })} /></label>)}</div><p className="cs-field__hint">One training job at a time. Publishing shared results and replacing an active model require review. Paid autopilot calls require a budget and model token prices.</p>{selectedProvider && !selectedProvider.local && <label className="cs-agent-disclosure"><input type="checkbox" checked={!!selectedDisclosure?.allowPrivate && selectedDisclosure.providerRevision === selectedProvider.revision} onChange={(event) => toggleDisclosure(event.target.checked)} /><span>Allow <strong>{selectedProvider.name}</strong> to receive relevant private notebook content, memory, and tool results.<small>{selectedProvider.baseUrl}</small></span></label>}<label className="cs-field"><span className="cs-field__label">Panel width</span><input type="range" min={340} max={640} step={10} value={width} onChange={(event) => setWidth(Number(event.target.value))} /></label><Button onClick={() => { void savePolicy(); }} disabled={busy}>Save settings</Button>
        <details className="cs-agent-automation"><summary>Continue research over time</summary><p className="cs-field__hint">Start a conversation first, then save its research goal and schedule. Saved autopilot limits apply to every wake-up.</p><label><input type="checkbox" checked={recurring} disabled={!threadId} onChange={(event) => setRecurring(event.target.checked)} /> Schedule this conversation</label><label className="cs-field"><span className="cs-field__label">Research goal</span><textarea className="cs-input" rows={3} value={researchGoal} onChange={(event) => setResearchGoal(event.target.value)} /></label><label className="cs-field"><span className="cs-field__label">Repeat every (hours)</span><input className="cs-input" type="number" min={1} max={8760} value={scheduleHours} onChange={(event) => setScheduleHours(Number(event.target.value))} /></label>{threadQuery.data?.automation?.nextWakeAt && <p className="cs-field__hint">Next: {new Date(threadQuery.data.automation.nextWakeAt).toLocaleString()}</p>}<Button disabled={busy || !threadId || (recurring && !researchGoal.trim())} onClick={() => { void saveSchedule(); }}>Save research schedule</Button></details>
        {background.data?.supported && <details className="cs-agent-automation"><summary>Background service</summary><p className="cs-field__hint">{background.data.installed ? "Installed. Research can continue after the desktop window closes while this Mac is awake." : "Install the optional macOS service to keep research running after quitting the desktop app."}</p><Button disabled={busy} onClick={() => { setBusy(true); void post("/api/agent-workspace/background", { action: background.data?.installed ? "uninstall" : "install" }).then(background.refresh).catch((e) => setError(messageOf(e))).finally(() => setBusy(false)); }}>{background.data.installed ? "Remove background service" : "Enable background service"}</Button></details>}
      </section>}
      {(error || providersQuery.error || threadsQuery.error || threadQuery.error) && <p className="cs-workspace-error" role="alert">{error ?? providersQuery.error ?? threadsQuery.error ?? threadQuery.error}</p>}
      <div className="cs-agent-messages" role="log" aria-label="Agent conversation messages" aria-live="polite">
        {!threadQuery.data?.messages?.length && <div className="cs-agent-welcome"><span aria-hidden="true">✦</span><h3>Start with a question.</h3><p>Research papers, organize notes, inspect structures, or prepare a training run. Your tools and saved memory are available here.</p>{["Find research relevant to my notes", "Inspect my datasets and suggest a training plan", "Continue my previous research"].map((prompt) => <button key={prompt} onClick={() => setDraft(prompt)}>{prompt} ↗</button>)}</div>}
        {threadQuery.data?.messages?.map((message) => message.kind === "tool_call" || message.kind === "tool_result" ? <details className={`cs-agent-tool cs-agent-tool--${message.kind}`} key={message.id}><summary>{message.kind === "tool_call" ? "Using tool" : "Tool result"} · {String(message.refs?.tool ?? message.refs?.name ?? message.refs?.toolName ?? "research step")}</summary><pre>{message.content}</pre></details> : <article key={message.id} className={`cs-agent-message cs-agent-message--${message.role}`}><span className="cs-kicker">{message.role === "assistant" ? "Studio agent" : message.role === "user" ? "You" : message.role}</span><Suspense fallback={<p>{message.content}</p>}><MarkdownPreview content={message.content} /></Suspense></article>)}
        {lastRun && <div className="cs-agent-run-status" role="status"><span className={activeRun ? "cs-live-dot" : ""} /><strong>{lastRun.status.replaceAll("_", " ")}</strong>{lastRun.modelId && <small>{lastRun.modelId}</small>}{activeRun ? <Button variant="ghost" onClick={() => { void post(`/api/agent-workspace/runs/${lastRun.id}/cancel`).then(threadQuery.refresh).catch((e) => setError(messageOf(e))); }}>Stop</Button> : ["failed", "cancelled", "budget_exhausted", "paused"].includes(lastRun.status) && <Button onClick={() => { void post(`/api/agent-workspace/runs/${lastRun.id}/resume`).then(threadQuery.refresh).catch((e) => setError(messageOf(e))); }}>Resume</Button>}{lastRun.error && <p className="cs-workspace-error">{lastRun.error}</p>}{lastRun.progress && <details><summary>Run progress</summary><StructuredData value={lastRun.progress} /></details>}</div>}
        <div ref={endRef} />
      </div>
      <form className="cs-agent-composer" onSubmit={(event) => { void send(event); }}><textarea className="cs-input" aria-label="Message research agent" placeholder="Ask, research, or build something…" rows={3} maxLength={32000} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><div className="cs-agent-composer-actions"><label><input type="checkbox" checked={autopilot} disabled={!policyQuery.data?.autopilot.enabled} onChange={(event) => setAutopilot(event.target.checked)} /> Autopilot</label><span className="cs-field__hint">⌘/Ctrl Enter</span><Button type="submit" variant="primary" disabled={busy || !!activeRun || !draft.trim()}>{busy ? "Starting…" : "Send"}</Button></div><p className="cs-field__hint">Private conversation · tools and results are recorded. Research findings remain linked to their sources.</p></form>
    </aside>}
  </>;
}
