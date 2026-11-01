import { useId, useRef, useState } from "react";
import { useMutation } from "react-relay";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { ProviderSaveMutation } from "./operations";
import { endpointError, endpointIsLocal, normalizedEndpoint, providerFailure } from "./providerDisplay";
import type { providersSettingsQuery } from "../../__generated__/providersSettingsQuery.graphql";
import type { providersSaveMutation } from "../../__generated__/providersSaveMutation.graphql";

export type InferenceProvider = providersSettingsQuery["response"]["inferenceProviders"][number];

export function ProviderForm({ provider, onSaved, onCancel, onBusyChange }: { provider?: InferenceProvider; onSaved: () => void; onCancel: () => void; onBusyChange?: (busy: boolean) => void }) {
  const protocolId = useId();
  const [commit, pending] = useMutation<providersSaveMutation>(ProviderSaveMutation);
  const submitting = useRef(false);
  const retryId = useRef<string | null>(null);
  const [name, setName] = useState(provider?.name ?? "");
  const [kind, setKind] = useState(provider?.kind ?? "openai");
  const [baseUrl, setBaseUrl] = useState(provider?.baseUrl ?? "https://api.openai.com/v1");
  const [model, setModel] = useState(provider?.model ?? "");
  const [apiStyle, setApiStyle] = useState(provider?.apiStyle ?? "responses");
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [enabled, setEnabled] = useState(provider?.enabled ?? false);
  const [supportsTools, setSupportsTools] = useState(provider?.supportsTools ?? true);
  const [error, setError] = useState<string | null>(null);
  const changedDestination = Boolean(provider?.hasApiKey && (kind !== provider.kind || normalizedEndpoint(baseUrl) !== normalizedEndpoint(provider.baseUrl)));
  const needsKeyDecision = changedDestination && !apiKey.trim() && !clearApiKey;
  const invalidEndpoint = endpointError(baseUrl);
  const valid = Boolean(name.trim() && model.trim() && baseUrl.trim() && !invalidEndpoint && !needsKeyDecision);
  const changed = (change: () => void) => { retryId.current = null; change(); };

  const submit = () => {
    if (!valid || pending || submitting.current) return;
    submitting.current = true; onBusyChange?.(true); setError(null);
    const clientMutationId = retryId.current ?? crypto.randomUUID();
    retryId.current = clientMutationId;
    commit({
      variables: { input: {
        ...(provider ? { id: provider.id, expectedRevision: provider.revision } : {}),
        name: name.trim(), kind, baseUrl: baseUrl.trim(), model: model.trim(), apiStyle, enabled, supportsTools,
        ...(apiKey.trim() ? { apiKey: apiKey.trim() } : {}), clearApiKey, clientMutationId,
      } },
      onCompleted: (response) => {
        submitting.current = false; onBusyChange?.(false);
        retryId.current = null;
        const result = response.providers.save;
        if (result.errors.length || !result.provider) { setError(providerFailure(result.errors[0]?.code, result.errors[0]?.fieldPath)); return; }
        setApiKey(""); onSaved();
      },
      onError: () => { submitting.current = false; onBusyChange?.(false); setError("Save could not be confirmed. Your entries are still here; retrying resumes the same request."); },
    });
  };

  return <form aria-label={provider ? "Edit provider" : "Add provider"} className="cs-provider-form" aria-busy={pending} onSubmit={(event) => { event.preventDefault(); submit(); }}>
    <TextField label="Provider name" value={name} onChange={(event) => changed(() => setName(event.target.value))} required disabled={pending} autoFocus placeholder="A name you will recognize in research" />
    <label className="cs-field"><span className="cs-field__label">Provider type</span><select className="cs-select" value={kind} disabled={pending} onChange={(event) => {
      changed(() => { const next = event.target.value; setKind(next);
      if (!provider) setApiStyle(next === "openai" ? "responses" : "chat_completions");
      if (next === "openai") setBaseUrl("https://api.openai.com/v1");
      else if (baseUrl === "https://api.openai.com/v1") setBaseUrl(""); });
    }}><option value="openai">OpenAI</option><option value="openai_compatible">OpenAI-compatible endpoint</option></select></label>
    <TextField label="API endpoint" type="url" value={baseUrl} disabled={pending} required onChange={(event) => changed(() => setBaseUrl(event.target.value))} error={invalidEndpoint} hint="Base URL including its API prefix, such as /v1. Local endpoints may use HTTP." autoComplete="off" spellCheck={false} />
    <div className="cs-field"><label className="cs-field__label" htmlFor={protocolId}>Provider API protocol</label><select id={protocolId} aria-describedby={`${protocolId}-hint`} className="cs-select" value={apiStyle} disabled={pending} onChange={(event) => changed(() => setApiStyle(event.target.value))}><option value="responses">Responses API</option><option value="chat_completions">Chat Completions</option></select><p id={`${protocolId}-hint`} className="cs-field__hint">Models inherit this protocol unless you configure an override below.</p></div>
    <TextField label="Model ID" value={model} onChange={(event) => changed(() => setModel(event.target.value))} disabled={pending} required hint="Enter the exact model identifier supported by this endpoint." autoComplete="off" spellCheck={false} />
    <fieldset className="cs-provider-key"><legend>API key</legend>
      <p className="cs-field__hint">{provider?.hasApiKey ? "A key is stored securely. It cannot be viewed here." : "No API key is stored. Local endpoints can work without one."}</p>
      <TextField label={provider?.hasApiKey ? "Replacement API key" : "New API key"} type="password" autoComplete="new-password" autoCapitalize="none" spellCheck={false} value={apiKey} disabled={pending || clearApiKey} onChange={(event) => changed(() => setApiKey(event.target.value))} error={needsKeyDecision ? "The destination changed. Replace or explicitly remove the saved key before saving." : undefined} hint={provider?.hasApiKey ? "Leave blank to retain the key only when the provider and endpoint stay unchanged." : "Optional for a local endpoint. A remote service may require a key."} />
      {provider?.hasApiKey && <label className="cs-provider-check"><input type="checkbox" checked={clearApiKey} disabled={pending} onChange={(event) => changed(() => { setClearApiKey(event.target.checked); if (event.target.checked) setApiKey(""); })} /><span>Remove saved API key</span></label>}
    </fieldset>
    <label className="cs-provider-check"><input type="checkbox" checked={enabled} disabled={pending} onChange={(event) => changed(() => setEnabled(event.target.checked))} /><span><strong>Make available in research</strong><small>Users must still choose this provider and allow data transfer for each turn.</small></span></label>
    <details className="cs-provider-options"><summary>Tool support</summary><label className="cs-provider-check"><input type="checkbox" checked={supportsTools} disabled={pending} onChange={(event) => changed(() => setSupportsTools(event.target.checked))} /><span><strong>Enable research tool calls</strong><small>Use only with a model that supports tool calls. Scientific review and approval gates still apply.</small></span></label></details>
    <div className="cs-provider-disclosure" role="note"><strong>{endpointIsLocal(baseUrl) ? "Local service" : "External provider"}</strong><p>{endpointIsLocal(baseUrl) ? "Research data will be sent to this local service, which may forward requests elsewhere." : "When selected for research, this endpoint receives task information, your question, recent user messages from this session and tool results from accessible workspace sources where export is allowed. Data leaves this Mac and provider usage may incur charges."} Saving these settings does not send research data or select the provider.</p></div>
    {error && <p className="cs-error" role="alert">{error}</p>}
    <div className="cs-provider-form-actions"><Button onClick={onCancel} disabled={pending}>Cancel</Button><Button variant="primary" type="submit" disabled={!valid || pending}>{pending ? "Saving…" : "Save provider"}</Button></div>
  </form>;
}
