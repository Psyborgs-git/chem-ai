import { useRef, useState } from "react";
import { useMutation } from "react-relay";
import { useNavigate } from "react-router";

import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { InlineFinding } from "../../components/molecules/InlineFinding";
import { ProjectCreateMutation } from "./operations";

import type { tasksProjectCreateMutation } from "../../__generated__/tasksProjectCreateMutation.graphql";

/** Project creation (§5.1/§11). The server owns validation —
 * the form shows whatever field errors it returns instead of
 * re-implementing rules client-side. On success the app enters the
 * new project (create → select is one step). */
export function ProjectCreateForm() {
  const navigate = useNavigate();
  const [commit, inFlight] = useMutation<tasksProjectCreateMutation>(
    ProjectCreateMutation,
  );
  const [customSlug, setCustomSlug] = useState("");
  const slugSuffix = useRef(crypto.randomUUID().slice(0, 6));
  const submitting = useRef(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [errors, setErrors] = useState<
    readonly { code: string; message: string }[]
  >([]);

  const generatedSlug = `${name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "project"}-${slugSuffix.current}`;
  const submit = () => {
    if (inFlight || submitting.current || !name.trim()) return;
    submitting.current = true;
    setErrors([]);
    commit({
      variables: {
        input: {
          slug: customSlug.trim() || generatedSlug,
          name,
          description: description || undefined,
        },
      },
      onCompleted: (resp) => {
        submitting.current = false;
        const errs = resp.projectCreate.errors;
        if (errs.length > 0) {
          setErrors(errs);
          return;
        }
        if (resp.projectCreate.project) {
          navigate(
            `/projects/${encodeURIComponent(resp.projectCreate.project.id)}`,
          );
        }
      },
      onError: (e) => {
        submitting.current = false;
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]);
      },
    });
  };

  return (
    <form aria-label="create project" aria-busy={inFlight} className="cs-project-create" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <TextField label="project name" hint="A name for the research you want to keep together." value={name} onChange={(event) => setName(event.target.value)} required autoFocus disabled={inFlight} />
      <details className="cs-create-details"><summary>Details <span>Optional</span></summary>
        <TextField label="description (optional)" value={description} onChange={(event) => setDescription(event.target.value)} disabled={inFlight} />
        <TextField label="project slug" hint={`Generated automatically: ${generatedSlug}. Set a custom identifier only if you need one.`} value={customSlug} onChange={(event) => setCustomSlug(event.target.value)} disabled={inFlight} />
      </details>
      {errors.map((error) => <InlineFinding key={`${error.code}:${error.message}`} severity="error" message={error.message} />)}
      <div className="cs-create-footer"><p>Add tasks and evidence as your research develops.</p><Button variant="primary" type="submit" disabled={inFlight || !name.trim()}>{inFlight ? "Creating…" : "Create project"}</Button></div>
    </form>
  );
}
