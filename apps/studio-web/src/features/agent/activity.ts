export type ActivityMessage = { id: string; role: string; kind: string; content: string; refs: Record<string, unknown> };
export type ActivityRow = { type: "message"; message: ActivityMessage } | { type: "tool"; id: string; name: string; call?: ActivityMessage; result?: ActivityMessage };
export function activityRows(messages: ActivityMessage[]): ActivityRow[] {
  const rows: ActivityRow[] = [];
  for (const message of messages) {
    if (!["tool_call", "tool_result"].includes(message.kind)) { rows.push({ type: "message", message }); continue; }
    const callId = message.refs?.toolCallId;
    const name = String(message.refs?.tool ?? message.refs?.name ?? message.refs?.toolName ?? "Research step");
    if (message.kind === "tool_result") {
      const previous = [...rows].reverse().find((row) => row.type === "tool" && !row.result && row.call && (callId ? row.call.refs?.toolCallId === callId : row.name === name));
      if (previous?.type === "tool") { previous.result = message; continue; }
    }
    rows.push({ type: "tool", id: message.id, name, ...(message.kind === "tool_call" ? { call: message } : { result: message }) });
  }
  return rows;
}
const names: Record<string, string> = { search_studio_docs: "Search documentation", read_studio_doc: "Read documentation", search_resources: "Search sources", fetch_resource: "Save source", read_resource: "Read source", create_notebook: "Create notebook", create_page: "Write note", update_page: "Update note", create_dataset: "Prepare dataset", freeze_dataset: "Freeze dataset", start_training_job: "Start training", await_training_job: "Wait for training", training_job_status: "Check training", calculate_smiles: "Calculate structure", learning_catalog: "Check runtimes", list_local_models: "Check models", register_local_model: "Add model", preview_local_model: "Test model", consult_role: "Review findings" };
export function activitySummary(row: Extract<ActivityRow, { type: "tool" }>): { title: string; detail: string; failed: boolean } {
  const title = names[row.name] ?? row.name.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
  if (!row.result) return { title, detail: "Working…", failed: false };
  try {
    const result = JSON.parse(row.result.content);
    if (result.ok === false || result.error) return { title, detail: typeof result.error === "string" ? result.error : String(result.error?.message ?? "Step needs attention"), failed: true };
    const envelope = result.data ?? result;
    if (envelope?.ok === false) return { title, detail: typeof envelope.error === "string" ? envelope.error : String(envelope.error?.message ?? "Step needs attention"), failed: true };
    const data = envelope?.ok === true && typeof envelope.untrusted === "boolean" && envelope.data ? envelope.data : envelope;
    const count = Array.isArray(data) ? data.length : Array.isArray(data.results) ? data.results.length : undefined;
    const detail = count !== undefined ? `${count} ${row.name === "search_studio_docs" ? count === 1 ? "article" : "articles" : row.name.includes("search") ? count === 1 ? "source" : "sources" : count === 1 ? "item" : "items"}` : data.name ?? data.title ?? data.state ?? data.status ?? "Done";
    return { title, detail: String(detail).replaceAll("_", " ").slice(0, 140), failed: false };
  } catch { return { title, detail: "Done", failed: false }; }
}

export type TranscriptRow = Extract<ActivityRow, { type: "message" }> | { type: "activity"; id: string; runId?: string; tools: Extract<ActivityRow, { type: "tool" }>[] };
/** One disclosure per user turn; exact calls and results remain inspectable inside it. */
export function transcriptRows(messages: (ActivityMessage & { runId?: string })[]): TranscriptRow[] {
  const rows: TranscriptRow[] = [];
  const groups = new Map<string, Extract<TranscriptRow, { type: "activity" }>>();
  let turn = "initial";
  const runIds = new Map(messages.map((message) => [message.id, message.runId]));
  for (const row of activityRows(messages)) {
    if (row.type === "message") {
      if (row.message.role === "user") turn = row.message.id;
      rows.push(row); continue;
    }
    const runId = runIds.get(row.call?.id ?? row.result?.id ?? row.id);
    const key = runId ?? turn;
    let group = groups.get(key);
    if (!group) { group = { type: "activity", id: row.id, runId, tools: [] }; groups.set(key, group); rows.push(group); }
    group.tools.push(row);
  }
  return rows;
}
