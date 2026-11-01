import { useId, useState, type FormEvent } from "react";
import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { Checkbox } from "../../components/atoms/Checkbox";
import { TextField } from "../../components/atoms/TextField";
import type { AgentModel, AgentProvider } from "../agent/AgentSidebar";
import { messageOf, post, useWorkspace } from "../workspace/useWorkspace";
import "../agent/agent.css";

const ROLES = ["planner", "researcher", "extractor", "reviewer"] as const;
type ModelApiStyle = "inherit" | "responses" | "chat_completions";
const protocolLabel = (style?: string) => style === "responses" ? "Responses API" : style === "chat_completions" ? "Chat Completions" : "Inherit provider";
type ModelDraft = {
  modelId: string; label: string; roles: string[]; enabled: boolean; supportsTools: boolean;
  inputPrice: string; outputPrice: string; apiStyle: ModelApiStyle;
};
const modelDraft = (model?: AgentModel): ModelDraft => ({
  modelId: model?.modelId ?? "", label: model?.label ?? "", roles: model?.roles ?? [...ROLES],
  enabled: model?.enabled ?? true, supportsTools: model?.supportsTools ?? false,
  apiStyle: model?.apiStyle === "responses" || model?.apiStyle === "chat_completions" ? model.apiStyle : "inherit",
  inputPrice: model?.inputPricePerMillionUsd == null ? "" : String(model.inputPricePerMillionUsd),
  outputPrice: model?.outputPricePerMillionUsd == null ? "" : String(model.outputPricePerMillionUsd),
});
function price(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100000) throw new Error("Enter token prices from 0 to 100,000 USD per million tokens, or leave them blank.");
  return parsed;
}

function ModelEditor({ provider, model, initialModelId, onSaved, onCancel }: {
  provider: AgentProvider; model?: AgentModel; initialModelId?: string;
  onSaved: () => Promise<void>; onCancel: () => void;
}) {
  const protocolId = useId();
  const [draft, setDraft] = useState<ModelDraft>(() => ({ ...modelDraft(model), ...(initialModelId && !model ? { modelId: initialModelId, label: initialModelId } : {}) }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const update = <K extends keyof ModelDraft,>(key: K, value: ModelDraft[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const save = async (event: FormEvent) => {
    event.preventDefault(); if (busy) return;
    setError(null); setBusy(true);
    try {
      if (!draft.modelId.trim()) throw new Error("Enter the exact model ID used by this provider.");
      await post(`/api/agent-workspace/providers/${provider.id}/models`, {
        modelId: draft.modelId.trim(), label: draft.label.trim() || draft.modelId.trim(),
        roles: draft.roles, enabled: draft.enabled, supportsTools: draft.supportsTools, apiStyle: draft.apiStyle,
        inputPricePerMillionUsd: price(draft.inputPrice), outputPricePerMillionUsd: price(draft.outputPrice),
      });
      await onSaved();
    } catch (e) { setError(messageOf(e)); } finally { setBusy(false); }
  };
  return <form className="cs-provider-model-form" aria-label={`${model ? "Edit" : "Add"} model for ${provider.name}`} onSubmit={(event) => void save(event)}>
    <TextField label="Model ID" value={draft.modelId} maxLength={160} required disabled={busy || Boolean(model)} onChange={(event) => update("modelId", event.target.value)} hint="Use the exact ID returned by the provider." />
    <TextField label="Display name" value={draft.label} maxLength={200} disabled={busy} onChange={(event) => update("label", event.target.value)} />
    <div className="cs-field"><label className="cs-field__label" htmlFor={protocolId}>Model API protocol</label><select id={protocolId} aria-describedby={`${protocolId}-hint`} className="cs-input" value={draft.apiStyle} disabled={busy} onChange={(event) => update("apiStyle", event.target.value as ModelApiStyle)}><option value="inherit">Inherit provider</option><option value="responses">Responses API</option><option value="chat_completions">Chat Completions</option></select><p id={`${protocolId}-hint`} className="cs-field__hint">Override the provider protocol when this model requires a different API.</p></div>
    <TextField label="Input price (USD / million tokens)" type="number" min="0" max="100000" step="any" value={draft.inputPrice} disabled={busy} onChange={(event) => update("inputPrice", event.target.value)} hint="Leave blank if unknown. Enter 0 only when usage is free." />
    <TextField label="Output price (USD / million tokens)" type="number" min="0" max="100000" step="any" value={draft.outputPrice} disabled={busy} onChange={(event) => update("outputPrice", event.target.value)} />
    <fieldset className="cs-model-role-checks"><legend>Available agent roles</legend>{ROLES.map((role) => <Checkbox key={role} label={role[0].toUpperCase() + role.slice(1)} checked={draft.roles.includes(role)} disabled={busy} onChange={(event) => update("roles", event.target.checked ? [...draft.roles, role] : draft.roles.filter((current) => current !== role))} />)}</fieldset>
    <Checkbox label="Available for selection" checked={draft.enabled} disabled={busy} onChange={(event) => update("enabled", event.target.checked)} />
    <Checkbox label="This model supports function tools" checked={draft.supportsTools} disabled={busy} onChange={(event) => update("supportsTools", event.target.checked)} />
    {error && <p className="cs-error" role="alert">{error}</p>}
    <div className="cs-actions"><Button type="submit" variant="primary" disabled={busy}>{busy ? "Saving model…" : "Save model"}</Button><Button onClick={onCancel} disabled={busy}>Cancel</Button></div>
  </form>;
}

function ModelGroup({ provider, canManage, onRefresh }: {
  provider: AgentProvider; canManage: boolean; onRefresh: () => Promise<void>;
}) {
  const [editor, setEditor] = useState<{ model?: AgentModel; modelId?: string } | null>(null);
  const [discovered, setDiscovered] = useState<string[] | null>(null);
  const [discoveredId, setDiscoveredId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selectId = useId();
  const discover = async () => {
    if (busy) return; setBusy("discover"); setError(null);
    try {
      const result = await post<{ models: { modelId: string }[] }>(`/api/agent-workspace/providers/${provider.id}/discover`);
      const models = [...new Set(result.models.map((model) => model.modelId))];
      setDiscovered(models); setDiscoveredId(models[0] ?? "");
    } catch (e) { setError(messageOf(e)); } finally { setBusy(null); }
  };
  const toggle = async (model: AgentModel) => {
    if (busy) return; setBusy(model.id); setError(null);
    try {
      await post(`/api/agent-workspace/providers/${provider.id}/models`, {
        modelId: model.modelId, label: model.label, roles: model.roles,
        supportsTools: model.supportsTools, enabled: !model.enabled, apiStyle: model.apiStyle ?? "inherit",
        inputPricePerMillionUsd: model.inputPricePerMillionUsd ?? null,
        outputPricePerMillionUsd: model.outputPricePerMillionUsd ?? null,
      });
      await onRefresh();
    } catch (e) { setError(messageOf(e)); } finally { setBusy(null); }
  };
  return <article className="cs-provider-model-group" aria-label={`${provider.name} models`}>
    <header><div><h3>{provider.name}</h3><p className="cs-field__hint">{provider.local ? "Local endpoint" : "External endpoint"} · {provider.models.length} configured {provider.models.length === 1 ? "model" : "models"}{!provider.enabled ? " · Provider disabled" : ""}</p></div>{canManage && <div className="cs-actions"><Button onClick={() => { setEditor({}); setError(null); }} disabled={Boolean(busy) || Boolean(editor)}>Add model</Button><Button onClick={() => void discover()} disabled={Boolean(busy) || Boolean(editor)}>{busy === "discover" ? "Listing models…" : "Discover models"}</Button></div>}</header>
    {discovered && <div className="cs-provider-discovery"><label className="cs-field__label" htmlFor={selectId}>{discovered.length ? "Models reported by this endpoint" : "This endpoint returned no model IDs"}</label>{discovered.length > 0 && <div className="cs-actions"><select id={selectId} className="cs-input" value={discoveredId} onChange={(event) => setDiscoveredId(event.target.value)}>{discovered.map((id) => <option value={id} key={id}>{id}</option>)}</select><Button disabled={!discoveredId || Boolean(editor)} onClick={() => setEditor({ model: provider.models.find((model) => model.modelId === discoveredId), modelId: discoveredId })}>Configure selected model</Button></div>}<p className="cs-field__hint">Discovery sends a model-list request to this endpoint. It does not send notebook content or verify tool support.</p></div>}
    <div className="cs-provider-model-rows">{provider.models.map((model) => <div className="cs-provider-model-row" key={model.id}>
      <div><strong>{model.label}</strong><small><code>{model.modelId}</code></small><small>{model.roles.length ? model.roles.join(", ") : "No roles assigned"} · {model.supportsTools ? "Function tools enabled" : "Function tools disabled"}</small><small>API: {protocolLabel(model.apiStyle)}</small><small>Input: {model.inputPricePerMillionUsd == null ? "price unknown" : `$${model.inputPricePerMillionUsd}/M`} · Output: {model.outputPricePerMillionUsd == null ? "price unknown" : `$${model.outputPricePerMillionUsd}/M`}</small></div>
      <Badge tone={model.enabled ? "info" : "neutral"}>{model.enabled ? "Available" : "Disabled"}</Badge>
      {canManage && <><Button aria-label={`Edit ${model.label}`} disabled={Boolean(busy) || Boolean(editor)} onClick={() => setEditor({ model })}>Edit</Button><Button aria-label={`${model.enabled ? "Disable" : "Enable"} ${model.label}`} disabled={Boolean(busy) || Boolean(editor)} onClick={() => void toggle(model)}>{busy === model.id ? "Saving…" : model.enabled ? "Disable" : "Enable"}</Button></>}
    </div>)}</div>
    {!provider.models.length && <p>No models configured for this connection.</p>}
    {editor && <ModelEditor key={editor.model?.id ?? editor.modelId ?? "new"} provider={provider} model={editor.model} initialModelId={editor.modelId} onCancel={() => setEditor(null)} onSaved={async () => { await onRefresh(); setEditor(null); }} />}
    {error && <p className="cs-error" role="alert">{error}</p>}
  </article>;
}

export function ProviderModelsPanel({ canManage }: { canManage: boolean }) {
  const query = useWorkspace<{ providers: AgentProvider[] }>("/api/agent-workspace/providers");
  const refresh = async () => { await query.refresh(); window.dispatchEvent(new Event("studio-provider-models-updated")); };
  return <section className="cs-provider-model-workspace" aria-labelledby="provider-models-title">
    <h2 id="provider-models-title">Models on each provider</h2>
    <p className="cs-field__hint">Keep one connection and credential per provider. Add the models you want to use for planning, research, extraction and review.</p>
    {query.loading && <p role="status">Loading configured models…</p>}
    {query.error && <div role="alert"><p className="cs-error">{query.error}</p><Button onClick={() => void query.refresh()}>Retry model list</Button></div>}
    {query.data?.providers.map((provider) => <ModelGroup key={provider.id} provider={provider} canManage={canManage} onRefresh={refresh} />)}
    {query.data?.providers.length === 0 && <p>Add a provider above to configure its models.</p>}
  </section>;
}
