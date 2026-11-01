import { useState } from "react";
import { CreateSheet } from "../../components/layout/CreateSheet";
import { TaskCreateForm } from "./TaskCreateForm";

export function ResearchSheet({ open, onClose, projects = [], projectId }: {
  open: boolean; onClose: () => void; projects?: readonly { id: string; name: string }[]; projectId?: string;
}) {
  const [selected, setSelected] = useState(projectId ?? "");
  return <CreateSheet open={open} onClose={onClose} title="Start a research task" description="Start with the question. You can add evidence and success criteria as you go.">
    {!projectId && <details className="cs-save-context"><summary>Organize in a project <span>Optional</span></summary><label htmlFor="research-project">Project</label><select className="cs-select" id="research-project" value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">Research inbox — organize automatically</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></details>}
    <TaskCreateForm projectId={projectId ?? (selected || undefined)} />
  </CreateSheet>;
}
