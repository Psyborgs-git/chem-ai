import { useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";
import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { CreateSheet } from "../../components/layout/CreateSheet";
import { PageHeader, StudioIcon } from "../../components/layout/StudioLayout";
import { ProviderForm, type InferenceProvider } from "./ProviderForm";
import { ProviderModelsPanel } from "./ProviderModelsPanel";
import { ProviderCleanupMutation, ProviderDeleteMutation, ProvidersQuery, ProviderTestMutation } from "./operations";
import { endpointIsLocal, providerFailure } from "./providerDisplay";
import type { providersSettingsQuery } from "../../__generated__/providersSettingsQuery.graphql";
import type { providersDeleteMutation } from "../../__generated__/providersDeleteMutation.graphql";
import type { providersTestMutation } from "../../__generated__/providersTestMutation.graphql";
import type { providersCleanupMutation } from "../../__generated__/providersCleanupMutation.graphql";
import "./providers.css";

type DialogState = { kind: "create" } | { kind: "edit" | "remove"; provider: InferenceProvider } | null;

function ProviderCard({ provider, canManage, busy, onEdit, onTest, onRemove }: { provider: InferenceProvider; canManage: boolean; busy: boolean; onEdit: () => void; onTest: () => void; onRemove: () => void }) {
  return <article className="cs-provider-card" aria-label={provider.name}>
    <header><span className="cs-provider-symbol"><StudioIcon name="providers" /></span><div><h2>{provider.name}</h2><p>{provider.kind === "openai" ? "OpenAI" : "OpenAI-compatible"} · {endpointIsLocal(provider.baseUrl) ? "Local endpoint" : "External endpoint"}</p></div><Badge tone={provider.enabled ? "info" : "neutral"}>{provider.enabled ? "Available for selection" : "Not available in research"}</Badge></header>
    <dl className="cs-provider-facts"><div><dt>Endpoint</dt><dd><code>{provider.baseUrl}</code></dd></div><div><dt>Default model</dt><dd><code>{provider.model}</code></dd></div><div><dt>API key</dt><dd>{provider.hasApiKey ? "Key stored securely" : "No key stored"}</dd></div><div><dt>Research tools</dt><dd>{provider.supportsTools ? "Enabled · existing approval gates apply" : "Not enabled"}</dd></div></dl>
    <div className="cs-provider-test-status"><Badge tone={provider.lastTestStatus === "reachable" ? "success" : provider.lastTestStatus === "failed" ? "danger" : "neutral"}>{provider.lastTestStatus === "reachable" ? "Endpoint reachable" : provider.lastTestStatus === "failed" ? "Connection check failed" : "Not tested"}</Badge>{provider.lastTestAt && <span>Last check: {new Date(provider.lastTestAt).toLocaleString()}</span>}</div>
    <p className="cs-field__hint">Provider protocol: {provider.apiStyle === "responses" ? "Responses API" : "Chat Completions"}. Connection checks list models only. Completion and tool compatibility are not verified.</p>
    {canManage && <div className="cs-provider-card-actions"><Button onClick={onEdit} disabled={busy}>Edit</Button><Button onClick={onTest} disabled={busy}>{busy ? "Working…" : "Test connection"}</Button><Button variant="ghost" onClick={onRemove} disabled={busy}>Remove</Button></div>}
  </article>;
}

export function ProvidersPage() {
  const [fetchKey, setFetchKey] = useState(0);
  const data = useLazyLoadQuery<providersSettingsQuery>(ProvidersQuery, {}, { fetchKey, fetchPolicy: "network-only" });
  const [dialog, setDialog] = useState<DialogState>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ error: boolean; text: string } | null>(null);
  const [testProvider] = useMutation<providersTestMutation>(ProviderTestMutation);
  const [removeProvider, removing] = useMutation<providersDeleteMutation>(ProviderDeleteMutation);
  const [cleanupCredentials, cleaning] = useMutation<providersCleanupMutation>(ProviderCleanupMutation);
  const canManage = data.canManageInferenceProviders;
  const refresh = () => setFetchKey((key) => key + 1);
  const close = () => { if (!formBusy && !removing) setDialog(null); };
  const saved = () => { setDialog(null); setNotice({ error: false, text: "Provider settings saved. Choose this provider explicitly in a research turn when you are ready." }); refresh(); };
  const test = (provider: InferenceProvider) => {
    if (busyId) return;
    setBusyId(provider.id); setNotice(null);
    testProvider({ variables: { input: { id: provider.id, clientMutationId: crypto.randomUUID() } }, onCompleted: (response) => {
      setBusyId(null);
      const result = response.providers.test;
      setNotice(result.errors.length ? { error: true, text: providerFailure(result.errors[0]?.code, result.errors[0]?.fieldPath) } : { error: result.status !== "reachable", text: result.status === "reachable" ? "The saved endpoint answered the models check. No research context was sent; completion and tool compatibility were not tested." : "The saved endpoint could not pass the models check. Check its URL and API key, then test again." });
      refresh();
    }, onError: () => { setBusyId(null); setNotice({ error: true, text: "The connection check could not be confirmed. Check that Chemistry Studio is running, then try again." }); } });
  };
  const remove = () => {
    if (dialog?.kind !== "remove" || removing) return;
    const provider = dialog.provider;
    removeProvider({ variables: { input: { id: provider.id, expectedRevision: provider.revision, clientMutationId: crypto.randomUUID() } }, onCompleted: (response) => {
      const result = response.providers.delete;
      if (result.errors.length || !result.deleted) { setNotice({ error: true, text: providerFailure(result.errors[0]?.code, result.errors[0]?.fieldPath) }); return; }
      setDialog(null);
      setNotice({ error: result.credentialCleanupPending, text: result.credentialCleanupPending ? "Provider removed. Secure key removal is pending. Unlock your macOS keychain, then choose Retry key cleanup." : "Provider and its saved key removed." }); refresh();
    }, onError: () => setNotice({ error: true, text: "Removal could not be confirmed. Reload the page before trying again." }) });
  };
  const cleanup = () => {
    if (cleaning) return;
    cleanupCredentials({ variables: {}, onCompleted: (response) => {
      const result = response.providers.cleanupCredentials;
      setNotice({ error: result.pending || result.errors.length > 0, text: result.pending ? "Some saved keys could not be removed. Unlock your macOS keychain, then choose Retry key cleanup again." : result.errors.length ? providerFailure(result.errors[0]?.code, result.errors[0]?.fieldPath) : "Retired API keys removed from secure storage." }); refresh();
    }, onError: () => setNotice({ error: true, text: "Key cleanup could not be confirmed. Check the local service and retry cleanup." }) });
  };

  return <div className="cs-providers-page">
    <PageHeader eyebrow="Workspace settings" title="AI providers" description="Connect an endpoint, then configure the models available to your research agent." actions={canManage ? <Button variant="primary" onClick={() => setDialog({ kind: "create" })}>Add provider</Button> : undefined} />
    <div className="cs-provider-privacy" role="note"><StudioIcon name="providers" /><div><strong>You control where research goes</strong><p>Saving or enabling a connection does not send task data. When you select a model, it receives the research question, relevant authorized context, conversation and tool results for that workflow. Sending private library content to an external provider requires your saved permission. Source rights and existing review requirements still apply. External usage may incur provider charges; configure model pricing below for budget tracking.</p></div></div>
    {!canManage && <p className="cs-provider-readonly" role="note">You can view these connections. A workspace administrator manages settings and API keys.</p>}
    {canManage && data.inferenceCredentialCleanupPending && <section className="cs-provider-cleanup" aria-label="Pending key cleanup"><div><strong>Saved key cleanup is pending</strong><p>Unlock your macOS keychain, then retry to remove retired credentials. Unlocking alone does not complete cleanup.</p></div><Button onClick={cleanup} disabled={cleaning}>{cleaning ? "Removing retired keys…" : "Retry key cleanup"}</Button></section>}
    {notice && dialog?.kind !== "remove" && <p role={notice.error ? "alert" : "status"} className={notice.error ? "cs-error" : "cs-provider-notice"}>{notice.text}</p>}
    {data.inferenceProviders.length ? <div className="cs-provider-list" aria-label="Saved providers">{data.inferenceProviders.map((provider) => <ProviderCard key={provider.id} provider={provider} canManage={canManage} busy={busyId === provider.id} onEdit={() => setDialog({ kind: "edit", provider })} onTest={() => test(provider)} onRemove={() => { setNotice(null); setDialog({ kind: "remove", provider }); }} />)}</div> : <section className="cs-provider-empty"><StudioIcon name="providers" /><h2>No providers connected</h2><p>Your local runtime and manual research remain available. Add a connection when you want to use an external or compatible local model.</p>{canManage && <Button onClick={() => setDialog({ kind: "create" })}>Connect your first provider</Button>}</section>}
    <ProviderModelsPanel key={fetchKey} canManage={canManage} />
    <CreateSheet open={dialog !== null} onClose={close} title={dialog?.kind === "create" ? "Add provider" : dialog?.kind === "edit" ? "Edit provider" : "Remove provider?"} description={dialog?.kind === "remove" ? "Remove this connection and its stored key." : "Keys are stored on the backend and are never returned to this page."}>
      {dialog?.kind === "create" && <ProviderForm key="create" onSaved={saved} onCancel={close} onBusyChange={setFormBusy} />}
      {dialog?.kind === "edit" && <ProviderForm key={dialog.provider.id} provider={dialog.provider} onSaved={saved} onCancel={close} onBusyChange={setFormBusy} />}
      {dialog?.kind === "remove" && <div className="cs-provider-remove"><p>Remove <strong>{dialog.provider.name}</strong>? Its connection settings and saved API key will be removed.</p>{notice?.error && <p role="alert" className="cs-error">{notice.text}</p>}<div className="cs-actions"><Button onClick={close} disabled={removing}>Cancel</Button><Button variant="danger" onClick={remove} disabled={removing}>{removing ? "Removing…" : "Remove provider"}</Button></div></div>}
    </CreateSheet>
  </div>;
}
