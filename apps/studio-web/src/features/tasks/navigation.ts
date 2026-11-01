/** Pure navigation metadata, shared without importing task screens. */
export const GROUPS = [
  { key: "overview", label: "Overview" },
  { key: "research", label: "Research" },
  { key: "candidates", label: "Candidates" },
  { key: "experiments", label: "Experiments" },
  { key: "evidence", label: "Sources" },
  { key: "decisions", label: "Review" },
  { key: "advanced", label: "Tools" },
] as const;

export type GroupKey = (typeof GROUPS)[number]["key"];

export const SUBVIEWS: Record<GroupKey, { key: string; label: string }[]> = {
  overview: [],
  research: [],
  candidates: [],
  experiments: [
    { key: "plans", label: "Plans" },
    { key: "calculations", label: "Calculations" },
    { key: "results", label: "Results" },
  ],
  evidence: [
    { key: "claims", label: "Claims" },
    { key: "quality", label: "Source quality" },
  ],
  decisions: [
    { key: "closeout", label: "Review & decide" },
    { key: "report", label: "Report" },
    { key: "log", label: "Decision history" },
  ],
  advanced: [
    { key: "runs", label: "Run history" },
    { key: "datasets", label: "Datasets" },
    { key: "training", label: "Training" },
    { key: "models", label: "Models" },
    { key: "evaluations", label: "Evaluations" },
    { key: "optimization", label: "Optimization" },
    { key: "analysis", label: "Reference analysis" },
  ],
};

export function isGroup(key: string | undefined): key is GroupKey {
  return GROUPS.some((group) => group.key === key);
}

export function defaultView(group: GroupKey): string | null {
  return SUBVIEWS[group][0]?.key ?? null;
}

export function taskUrl(taskId: string, group: GroupKey, view?: string | null) {
  const base = `/tasks/${encodeURIComponent(taskId)}/${group}`;
  return view ? `${base}?view=${view}` : base;
}
