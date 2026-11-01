import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentSidebar } from "./AgentSidebar";
const state = vi.hoisted(() => ({ refresh: vi.fn(), post: vi.fn(), request: vi.fn(), providers: [] as unknown[], history: null as any, search: null as any, thread: null as any, threadStatus: null as number | null, lastHistoryPath: "" }));
const provider = { id: "provider-one", revision: 1, name: "Research provider", baseUrl: "https://example.org/v1", enabled: true, local: false, models: [{ id: "child-one", modelId: "research-model", label: "Research model", roles: ["planner"], enabled: true, supportsTools: true }] };
const thread = { id: "thread-one", title: "Silk research", updatedAt: "2026-11-01T10:00:00Z", messages: [{ id: "user", runId: "run", role: "user", kind: "message", content: "Find sources about silk", refs: {} }, { id: "call", runId: "run", role: "assistant", kind: "tool_call", content: '{"arguments":{"query":"silk"}}', refs: { tool: "search_resources", toolCallId: "search-one" } }, { id: "result", runId: "run", role: "tool", kind: "tool_result", content: '{"ok":true,"data":{"results":[{"title":"Silk paper"}]}}', refs: { tool: "search_resources", toolCallId: "search-one" } }, { id: "answer", runId: "run", role: "assistant", kind: "message", content: "I saved the relevant source.", refs: {} }], runs: [{ id: "run", status: "completed", providerId: "provider-one", modelId: "research-model", role: "researcher" }] };
const summary = { id: thread.id, title: thread.title, updatedAt: thread.updatedAt, messageCount: 2, lastMessagePreview: "I saved the relevant source.", lastRunStatus: "completed" };
const empty: unknown[] = [];
vi.mock("../../relay/network", () => ({ rawUuid: (value: string) => value, workspaceRequest: state.request }));
vi.mock("../workspace/useWorkspace", () => ({ post: state.post, messageOf: (error: Error) => error.message, useWorkspace: (path: string | null) => {
  let data: unknown = null, errorStatus: number | null = null;
  if (path === "/api/agent-workspace/providers") data = state.providers;
  else if (path?.startsWith("/api/agent-workspace/threads?")) { state.lastHistoryPath = path; data = new URL(path, "http://localhost").searchParams.get("q") ? state.search : state.history; }
  else if (path?.startsWith("/api/agent-workspace/threads/")) { data = state.thread?.id === path.split("/").at(-1) ? state.thread : null; errorStatus = state.threadStatus; }
  else if (path === "/api/learning-workspace/models") data = empty;
  return { data, refresh: state.refresh, error: errorStatus ? "Chat request failed" : null, errorStatus, loading: false };
} }));
vi.mock("../notebooks/MarkdownPreview", () => ({ MarkdownPreview: ({ content }: { content: string }) => <div>{content}</div> }));
beforeEach(() => { localStorage.clear(); state.providers = [provider]; state.history = { threads: [summary], nextOffset: null, query: "", ownerScope: "workspace:alice" }; state.search = { threads: [], nextOffset: null, query: "needle", ownerScope: "workspace:alice" }; state.thread = thread; state.threadStatus = null; state.refresh.mockReset().mockResolvedValue(undefined); state.post.mockReset().mockImplementation(async (path: string) => path === "/api/agent-workspace/threads" ? { id: "new-thread", title: "New chat" } : {}); state.request.mockReset(); vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })); Element.prototype.scrollIntoView = vi.fn(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function mount() { return render(<MemoryRouter><AgentSidebar /></MemoryRouter>); }
function openPanel() { fireEvent.click(screen.getByRole("button", { name: "Open research agent" })); }
function openSaved() { openPanel(); fireEvent.click(screen.getByRole("button", { name: "Open chat: Silk research" })); }
describe("familiar agent chat", () => {
  it("makes history and New chat visible, then defaults a new chat to the configured model", async () => {
    mount(); openPanel();
    expect(screen.getByRole("region", { name: "Chat history" })).toBeVisible();
    expect(screen.getByRole("button", { name: /New chat/ })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /New chat/ }));
    expect(screen.getByRole("combobox", { name: "Agent model" })).toHaveTextContent("Research model · Research provider");
    expect(screen.getByLabelText("Message research agent")).toHaveFocus();
    expect(screen.getByRole("button", { name: /Send/ })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Message research agent"), { target: { value: "Compare silk references" } });
    fireEvent.submit(screen.getByLabelText("Message research agent").closest("form")!);
    await waitFor(() => expect(state.post).toHaveBeenCalledWith("/api/agent-workspace/threads/new-thread/runs", expect.objectContaining({ providerId: "provider-one", modelId: "research-model", message: "Compare silk references" })));
    expect(screen.queryByLabelText("Agent provider")).toBeNull();
  });
  it("uses authoritative title-and-message search results and exposes pagination", async () => {
    state.history = { ...state.history, threads: [summary, { ...summary, id: "other", title: "Another chat" }], nextOffset: 50 };
    state.search = { threads: [{ ...summary, title: "Unrelated title", lastMessagePreview: "A different last answer" }], nextOffset: null, query: "needle", ownerScope: "workspace:alice" };
    mount(); openPanel(); expect(screen.getByRole("button", { name: "Load older chats" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Search chats"), { target: { value: "needle" } });
    await waitFor(() => expect(state.lastHistoryPath).toContain("q=needle"));
    await screen.findByRole("button", { name: "Open chat: Unrelated title" });
    expect(screen.queryByRole("button", { name: "Open chat: Another chat" })).toBeNull();
  });
  it("keeps Send disabled when no configured model is available", () => {
    state.providers = [];
    mount(); openPanel(); fireEvent.click(screen.getByRole("button", { name: /New chat/ }));
    fireEvent.change(screen.getByLabelText("Message research agent"), { target: { value: "Review my research" } });
    expect(screen.getByText("Choose a model to begin")).toBeVisible();
    expect(screen.getByRole("button", { name: /Send/ })).toBeDisabled();
  });
  it("loads persisted chats, groups tool work, and keeps technical payloads collapsed", async () => {
    mount(); openSaved();
    expect(screen.getByRole("heading", { name: "Silk research" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Agent model" })).toHaveTextContent("Research model · Research provider");
    const log = screen.getByRole("log", { name: "Agent conversation messages" });
    expect(within(log).getByText("· 1 step")).toBeVisible();
    expect(within(log).queryByText(/Silk paper/)).toBeNull();
    fireEvent.click(within(log).getByText("· 1 step").closest("summary")!);
    await waitFor(() => expect(within(log).getByText("1 source")).toBeVisible());
    fireEvent.click(within(log).getByText("Technical details"));
    await waitFor(() => expect(within(log).getByText(/Silk paper/)).toBeVisible());
  });
  it("preserves a draft when starting a new chat or opening a contextual request", () => {
    mount(); openSaved(); fireEvent.change(screen.getByLabelText("Message research agent"), { target: { value: "My unsent thought" } });
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    fireEvent(window, new CustomEvent("studio-agent-open", { detail: { notebookId: "new-notebook", message: "Review this note" } }));
    expect(screen.getByLabelText("Message research agent")).toHaveValue("Review this note");
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    fireEvent.click(screen.getByRole("button", { name: "Open chat: Silk research" }));
    expect(screen.getByLabelText("Message research agent")).toHaveValue("My unsent thought");
  });
  it("keeps the original unsent New chat draft separate from a contextual Ask draft", () => {
    mount(); openPanel(); fireEvent.click(screen.getByRole("button", { name: /New chat/ }));
    fireEvent.change(screen.getByLabelText("Message research agent"), { target: { value: "My unsent new research idea" } });
    fireEvent(window, new CustomEvent("studio-agent-open", { detail: { notebookId: "notebook-context", message: "Review this notebook" } }));
    expect(screen.getByLabelText("Message research agent")).toHaveValue("Review this notebook");
    fireEvent.change(screen.getByLabelText("Message research agent"), { target: { value: "Review this notebook and its retained sources" } });
    fireEvent.click(screen.getByRole("button", { name: /New chat/ }));
    expect(screen.getByLabelText("Message research agent")).toHaveValue("My unsent new research idea");
    fireEvent(window, new CustomEvent("studio-agent-open", { detail: { notebookId: "notebook-context", message: "Default Ask text" } }));
    expect(screen.getByLabelText("Message research agent")).toHaveValue("Review this notebook and its retained sources");
    fireEvent.click(screen.getByRole("button", { name: /New chat/ }));
    expect(screen.getByLabelText("Message research agent")).toHaveValue("My unsent new research idea");
    expect(state.post).not.toHaveBeenCalled();
  });
  it("restores only an owner-scoped thread ID across a remount and clears foreign-owner content", async () => {
    const first = mount(); openSaved();
    await waitFor(() => expect(localStorage.getItem("studio.agent.activeThread:workspace:alice")).toBe("thread-one"));
    expect(Object.values(localStorage)).not.toContain(thread.title);
    first.unmount(); const second = mount(); openPanel();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Silk research" })).toBeVisible());
    state.history = { threads: [], nextOffset: null, query: "", ownerScope: "workspace:bob" };
    second.rerender(<MemoryRouter><AgentSidebar /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole("region", { name: "Chat history" })).toBeVisible());
    expect(screen.queryByText("I saved the relevant source.")).toBeNull();
    expect(localStorage.getItem("studio.agent.activeThread:workspace:bob")).toBeNull();
  });
  it.each([404, 500])("clears an unavailable saved selection only for a 404, not a %i transient error", async (status) => {
    localStorage.setItem("studio.agent.activeThread:workspace:alice", "unavailable-chat"); state.thread = null; state.threadStatus = status;
    mount(); openPanel();
    if (status === 404) { await screen.findByText("That chat is no longer available. Choose another chat."); expect(localStorage.getItem("studio.agent.activeThread:workspace:alice")).toBeNull(); }
    else { await waitFor(() => expect(screen.getByRole("region", { name: "Current chat" })).toBeVisible()); expect(localStorage.getItem("studio.agent.activeThread:workspace:alice")).toBe("unavailable-chat"); }
  });
  it("restores a first run arriving later and preserves manual model choice within that same run", async () => {
    state.thread = { ...thread, runs: [] };
    const view = mount(); fireEvent(window, new CustomEvent("studio-agent-open", { detail: { threadId: "thread-one" } }));
    expect(screen.getByRole("combobox", { name: "Agent model" })).toHaveTextContent("Choose a model");
    state.thread = thread; view.rerender(<MemoryRouter><AgentSidebar /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Agent model" })).toHaveTextContent("Research model · Research provider"));
    await userEvent.click(screen.getByRole("combobox", { name: "Agent model" }));
    await userEvent.click(await screen.findByRole("option", { name: "Local llama.cpp runtime" }));
    view.rerender(<MemoryRouter><AgentSidebar /></MemoryRouter>);
    expect(screen.getByRole("combobox", { name: "Agent model" })).toHaveTextContent("Local llama.cpp runtime");
  });
  it("replaces Send with Stop while work is active and does not resume just by opening history", async () => {
    state.thread = { ...thread, runs: [{ ...thread.runs[0], status: "running" }] };
    mount(); openSaved();
    expect(screen.queryByRole("button", { name: /Send/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Stop/ })).toBeVisible(); expect(state.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Stop/ }));
    await waitFor(() => expect(state.post).toHaveBeenCalledWith("/api/agent-workspace/runs/run/cancel"));
  });
  it("makes long operator prompts expandable and supports a wider chat workspace", async () => {
    const long = `${"Research the material with its sources. ".repeat(30)}PRIVATE-LONG-PROMPT-END`;
    state.thread = { ...thread, messages: [{ ...thread.messages[0], content: long }, ...thread.messages.slice(1)] };
    mount(); openSaved();
    expect(screen.queryByText(/PRIVATE-LONG-PROMPT-END/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show full message" }));
    await screen.findByText(/PRIVATE-LONG-PROMPT-END/);
    fireEvent.click(screen.getByRole("button", { name: "Expand chat" }));
    expect(screen.getByRole("complementary", { name: "Research agent" })).toHaveClass("is-expanded");
    expect(screen.getByRole("region", { name: "Chat history" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Current chat" })).toBeVisible();
  });
  it("supports keyboard model selection and restores focus without closing the chat", async () => {
    mount(); openSaved();
    const trigger = screen.getByRole("combobox", { name: "Agent model" });
    trigger.focus();
    await userEvent.keyboard("{ArrowDown}");
    await screen.findByRole("listbox");
    await userEvent.keyboard("{End}{Enter}");
    await waitFor(() => expect(trigger).toHaveTextContent("Local llama.cpp runtime"));
    await waitFor(() => expect(trigger).toHaveFocus());
    await userEvent.keyboard("{ArrowDown}");
    await screen.findByRole("listbox");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    expect(screen.getByRole("complementary", { name: "Research agent" })).toBeVisible();
    expect(trigger).toHaveFocus();
  });
  it("uses a focus-trapped settings dialog with real tabs and explicit private access", async () => {
    mount(); openSaved();
    const settings = screen.getByRole("button", { name: "Agent settings" });
    await userEvent.click(settings);
    const dialog = await screen.findByRole("dialog", { name: "Chat settings" });
    const width = within(dialog).getByRole("slider", { name: /Panel width/ });
    width.focus(); await userEvent.keyboard("{ArrowRight}");
    expect(width).toHaveAttribute("aria-valuenow", "490");
    const access = within(dialog).getByRole("switch", { name: /Private research access/ });
    expect(access).toHaveAttribute("aria-checked", "false");
    await userEvent.click(access);
    await userEvent.click(within(dialog).getByRole("tab", { name: "Autopilot" }));
    await userEvent.click(within(dialog).getByRole("switch", { name: /Enable autopilot/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(state.request).toHaveBeenCalledWith("/api/agent-workspace/policies", expect.objectContaining({ method: "PUT" })));
    const body = JSON.parse(state.request.mock.calls.find(([path]) => path === "/api/agent-workspace/policies")![1].body);
    expect(body.remoteDisclosure).toEqual({ providerId: "provider-one", providerRevision: 1, allowPrivate: true });
    expect(body.autopilot.enabled).toBe(true);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(settings).toHaveFocus();
    expect(screen.getByRole("complementary", { name: "Research agent" })).toBeVisible();
  });
  it("loads earlier messages without losing them when the newest page polls again", async () => {
    state.thread = { ...thread, hasEarlierMessages: true, oldestMessageId: "user" };
    state.request.mockResolvedValue({ id: thread.id, messages: [{ id: "old", role: "user", kind: "message", content: "Earlier textile idea", refs: {} }], hasEarlierMessages: false, oldestMessageId: "old" });
    const view = mount(); openSaved(); fireEvent.click(screen.getByRole("button", { name: "Load earlier messages" }));
    await screen.findByText("Earlier textile idea");
    state.thread = { ...state.thread, messages: [...thread.messages] }; view.rerender(<MemoryRouter><AgentSidebar /></MemoryRouter>);
    expect(screen.getByText("Earlier textile idea")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Load earlier messages" })).toBeNull();
    expect(state.request).toHaveBeenCalledWith("/api/agent-workspace/threads/thread-one?before=user&limit=500");
  });
  it("resets a disjoint latest page after background work so its missing middle remains loadable", async () => {
    mount(); openSaved();
    expect(screen.getByText("I saved the relevant source.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Close agent" }));
    state.thread = { ...thread, hasEarlierMessages: true, oldestMessageId: "latest-window-start", messages: [{ id: "latest-window-start", role: "user", kind: "message", content: "Continue after the long background run", refs: {} }, { id: "latest-answer", role: "assistant", kind: "message", content: "Latest saved research answer", refs: {} }] };
    state.request.mockResolvedValue({ id: thread.id, messages: [{ id: "middle", role: "assistant", kind: "message", content: "The intervening research observations", refs: {} }], hasEarlierMessages: false, oldestMessageId: "middle" });
    openPanel();
    await screen.findByText("Latest saved research answer");
    expect(screen.queryByText("I saved the relevant source.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Load earlier messages" }));
    await screen.findByText("The intervening research observations");
    expect(state.request).toHaveBeenCalledWith("/api/agent-workspace/threads/thread-one?before=latest-window-start&limit=500");
    expect(screen.getByText("Latest saved research answer")).toBeVisible();
  });
  it("saves the schedule from its tab-specific footer instead of silently saving only policy", async () => {
    mount(); openSaved(); await userEvent.click(screen.getByRole("button", { name: "Agent settings" }));
    const dialog = await screen.findByRole("dialog", { name: "Chat settings" });
    await userEvent.click(within(dialog).getByRole("tab", { name: "Schedule" }));
    expect(within(dialog).queryByRole("button", { name: "Save settings" })).toBeNull();
    await userEvent.type(within(dialog).getByLabelText("Research goal"), "Review the retained silk sources");
    await userEvent.click(within(dialog).getByRole("switch", { name: /Schedule this chat/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save research schedule" }));
    await waitFor(() => expect(state.request).toHaveBeenCalledWith("/api/agent-workspace/threads/thread-one/automation", expect.objectContaining({ method: "PUT" })));
    const body = JSON.parse(state.request.mock.calls.find(([path]) => path.endsWith("/automation"))![1].body);
    expect(body).toMatchObject({ enabled: true, researchGoal: "Review the retained silk sources", providerId: "provider-one", modelId: "research-model" });
    expect(state.request.mock.calls.some(([path]) => path === "/api/agent-workspace/policies")).toBe(false);
  });
});
