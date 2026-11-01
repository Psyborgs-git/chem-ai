import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Button } from "../../components/atoms/Button";
import { Badge } from "../../components/atoms/Badge";
import { ChemistryArt } from "../../components/layout/ChemistryArt";
import { StructuredData } from "../../components/layout/StudioLayout";
import { ContractEditor } from "./ContractEditor";

type Json = Record<string, unknown>;
type Contract = { revision: number; status: string; payload?: unknown };
function records(value: unknown): Json[] {
  return Array.isArray(value) ? value.filter((item): item is Json => item !== null && typeof item === "object" && !Array.isArray(item)) : [];
}
function target(metric: Json): string {
  if (typeof metric.target === "string" && metric.target.trim()) return metric.target;
  if (metric.target && typeof metric.target === "object" && "value" in metric.target) {
    const recorded = metric.target as Json;
    return `${String(recorded.value)}${recorded.unit ? ` ${String(recorded.unit)}` : ""}`;
  }
  const values = metric.target_values ?? metric.targetValues;
  const operators: Record<string, string> = { gte: "≥", lte: "≤", gt: ">", lt: "<", eq: "=", between: "between" };
  if (Array.isArray(values) && values.length) return `${operators[String(metric.operator)] ?? String(metric.operator ?? "")} ${values.join(" – ")}${metric.unit ? ` ${String(metric.unit)}` : ""}`;
  return "Target not recorded";
}

/** The overview is a readable checkpoint; criteria editing is an intentional action. */
export function TaskOverview({ taskId, workflowState, contract, onCriteriaSaved }: { taskId: string; workflowState: string; contract: Contract | null; onCriteriaSaved?: () => void }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get("edit") === "criteria";
  const [editing, setEditing] = useState(requested);
  useEffect(() => { if (requested) setEditing(true); }, [requested]);
  const payload = contract?.payload && typeof contract.payload === "object" ? contract.payload as Json : {};
  const metrics = records(payload.metrics ?? payload.requiredMetrics);
  const rawGates = payload.hard_constraints ?? payload.hardConstraints;
  const gates = Array.isArray(rawGates) ? rawGates : [];
  const edit = () => { const next = new URLSearchParams(params); next.set("edit", "criteria"); setParams(next); setEditing(true); };
  const done = () => { const next = new URLSearchParams(params); next.delete("edit"); setParams(next); setEditing(false); };

  if (editing) return <section className="cs-overview-editor" aria-label="Edit success criteria"><header><div><p className="cs-eyebrow">Define what success means</p><h2>Success criteria</h2></div><Button variant="ghost" onClick={done}>Back to overview</Button></header><ContractEditor taskId={taskId} workflowState={workflowState} onSaved={onCriteriaSaved} /></section>;
  if (!contract) return <section className="cs-overview-prompt" aria-label="Define success criteria"><ChemistryArt kind="research" className="cs-overview-art" /><div><p className="cs-eyebrow">Your next research checkpoint</p><h2>What would count as success?</h2><p>Set the questions you want to answer and the evidence you will need. Calculations can help you explore while these criteria are still a draft.</p><Button variant="primary" onClick={edit}>Define success criteria</Button></div></section>;
  return <section className="cs-overview-criteria" aria-label="Success criteria summary"><header><div><p className="cs-eyebrow">Your research checkpoint</p><h2>Success criteria <Badge tone={contract.status === "frozen" ? "info" : "neutral"}>{contract.status}</Badge></h2><p>Revision {contract.revision} · {metrics.length} recorded metric{metrics.length === 1 ? "" : "s"}</p></div><Button onClick={edit}>Edit criteria</Button></header>
    {metrics.length ? <ul className="cs-criteria-preview">{metrics.map((metric, index) => <li key={String(metric.id ?? index)}><div><strong>{String(metric.label ?? metric.name ?? metric.id ?? `Metric ${index + 1}`)}</strong><small>{metric.required === false ? "Optional criterion" : "Required criterion"}</small></div><div><span className="cs-criteria-target">{target(metric)}</span>{metric.conditions != null && <div className="cs-criteria-conditions"><StructuredData value={metric.conditions} /></div>}</div></li>)}</ul> : <p className="cs-field__hint">No structured metrics recorded. Review this revision to define the criteria explicitly.</p>}
    {gates.length > 0 && <details className="cs-technical"><summary>Hard constraints · {gates.length}</summary><StructuredData value={gates} /></details>}
  </section>;
}
