import { useRef, useState } from "react";
import { Link } from "react-router";
import { useMutation } from "react-relay";
import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { endpointIsLocal } from "../providers/providerDisplay";
import { TurnCancelMutation, TurnRequestMutation } from "./operations";
import type { researchTurnCancelMutation } from "../../__generated__/researchTurnCancelMutation.graphql";
import type { researchTurnRequestMutation } from "../../__generated__/researchTurnRequestMutation.graphql";
import "../providers/providers.css";

export type ResearchProvider = { readonly id: string; readonly revision: number; readonly name: string; readonly model: string; readonly baseUrl: string; readonly enabled: boolean };
type Notice = { tone: "info" | "warning" | "danger"; text: string };

/** An explicit provider and per-turn consent are part of the request identity. */
export function ResearchComposer({ sessionId, providers, onProvidersChanged }: { sessionId: string; providers: readonly ResearchProvider[]; onProvidersChanged?: () => void }) {
  const [turnRequest, requesting] = useMutation<researchTurnRequestMutation>(TurnRequestMutation);
  const [turnCancel, cancelling] = useMutation<researchTurnCancelMutation>(TurnCancelMutation);
  const [draft, setDraft] = useState("");
  const [providerId, setProviderId] = useState("");
  const [consentRevision, setConsentRevision] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [inflightTurn, setInflightTurn] = useState<string | null>(null);
  const [cancelSent, setCancelSent] = useState(false);
  const pending = useRef(false);
  const retryTurnId = useRef<string | null>(null);
  const selected = providers.find((provider) => provider.id === providerId && provider.enabled);
  const revision = selected ? `${selected.id}:${selected.revision}` : null;
  const consent = revision !== null && consentRevision === revision;
  const unavailable = Boolean(providerId && !selected);
  const allowed = !providerId || Boolean(selected && consent);

  const send = () => {
    const content = draft.trim();
    if (!content || requesting || pending.current || !allowed) return;
    pending.current = true;
    const turnId = retryTurnId.current ?? crypto.randomUUID();
    retryTurnId.current = turnId;
    setInflightTurn(turnId); setCancelSent(false); setNotice(null);
    turnRequest({
      variables: { input: { sessionId, content, turnId, ...(selected ? { providerId: selected.id, providerRevision: selected.revision, allowProviderDataTransfer: true } : {}) } },
      onCompleted: (response) => {
        pending.current = false; retryTurnId.current = null; setInflightTurn(null);
        const result = response.research.turnRequest;
        if (result.errors.length) {
          if (selected && result.errors.some((error) => error.code === "CONFLICT" && error.fieldPath === "providerRevision")) {
            setNotice({ tone: "danger", text: "Provider settings changed. Review the refreshed endpoint and model, then allow this turn again. No data was sent using stale settings." });
            onProvidersChanged?.();
          } else setNotice({ tone: "danger", text: "The research request was not accepted. Check your session, provider selection and permission to send data, then try again." });
          setConsentRevision(null); return;
        }
        if (result.finishedReason === "model_unavailable") setNotice({ tone: "warning", text: "model unavailable — no configured model responded; the question is recorded and manual work is unaffected. Review the recorded activity before sending again; that creates a new turn." });
        else if (result.finishedReason === "cancelled") setNotice({ tone: "info", text: "turn cancelled. Review the recorded activity before sending again; that creates a new turn." });
        else if (result.finishedReason !== "final") setNotice({ tone: "warning", text: "The turn ended before a final response. Your question is recorded. Review the activity before sending again; that creates a new turn." });
        if (result.finishedReason === "final") setDraft("");
        setConsentRevision(null);
      },
      onError: () => {
        pending.current = false; setInflightTurn(null);
        setNotice({ tone: "danger", text: "This request could not be confirmed. Your question is still here; retrying resumes the same request." });
      },
    });
  };
  const cancel = () => {
    if (!inflightTurn || cancelSent) return;
    setCancelSent(true);
    turnCancel({ variables: { input: { sessionId, turnId: inflightTurn } }, onError: () => setNotice({ tone: "danger", text: "Cancellation could not be confirmed. Wait for the recorded turn status before retrying." }) });
  };

  return <form aria-label="research composer" onSubmit={(event) => { event.preventDefault(); send(); }}>
    <div className="cs-research-provider">
      <label className="cs-field"><span className="cs-field__label">Research model</span><select className="cs-select" value={providerId} disabled={requesting} onChange={(event) => { setProviderId(event.target.value); setConsentRevision(null); retryTurnId.current = null; }}>
        <option value="">Local runtime (no saved provider)</option>
        {unavailable && <option value={providerId} disabled>Selected provider is unavailable</option>}
        {providers.filter((provider) => provider.enabled).map((provider) => <option key={provider.id} value={provider.id}>{provider.name} · {provider.model}</option>)}
      </select></label>
      <Link className="cs-research-provider__link" to="/settings/providers">Manage providers</Link>
      {!providerId && <p className="cs-field__hint">If no local model is running, the question is recorded and an unavailable status is shown.</p>}
      {unavailable && <p role="alert" className="cs-error">This provider is no longer available. Choose another connection or the local runtime.</p>}
      {selected && <div className="cs-research-provider__consent" role="group" aria-label="Provider data transfer">
        <p><strong>{endpointIsLocal(selected.baseUrl) ? "Local provider endpoint" : "External provider · data leaves this Mac"}</strong><br/><code>{selected.baseUrl}</code></p>
        <p>This turn sends the task ID, title, mode, your question, recent user messages from this session (up to 12 messages and 12,000 characters; long text may be truncated), and returned tool data. Research tools can return information from workspace sources you can access only when export is allowed; other source contents are withheld. Previous assistant outputs, earlier tool outputs and whole files are not attached automatically. {endpointIsLocal(selected.baseUrl) ? "This local service may forward requests elsewhere." : "Provider usage may incur charges."}</p>
        <label className="cs-provider-check"><input type="checkbox" checked={consent} disabled={requesting} onChange={(event) => { setConsentRevision(event.target.checked ? revision : null); retryTurnId.current = null; }} /><span>Allow this provider to receive data for this turn</span></label>
      </div>}
    </div>
    <TextField label="ask the research agent" value={draft} disabled={requesting} onChange={(event) => { setDraft(event.target.value); retryTurnId.current = null; }} />
    {requesting ? <Button onClick={cancel} disabled={cancelling || cancelSent}>{cancelSent ? "cancel requested…" : "cancel turn"}</Button> : <Button type="submit" disabled={!draft.trim() || !allowed}>send</Button>}
    {notice && <p role={notice.tone === "danger" ? "alert" : "status"}><Badge tone={notice.tone}>{notice.text}</Badge></p>}
  </form>;
}
