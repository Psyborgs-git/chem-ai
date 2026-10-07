import { useState } from "react";
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
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [errors, setErrors] = useState<
    readonly { code: string; message: string }[]
  >([]);

  const submit = () => {
    setErrors([]);
    commit({
      variables: {
        input: {
          slug,
          name,
          description: description || undefined,
        },
      },
      onCompleted: (resp) => {
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
      onError: (e) =>
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]),
    });
  };

  return (
    <form
      aria-label="create project"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <TextField
        label="project slug"
        hint="short lowercase id, e.g. solvent-study"
        value={slug}
        onChange={(e) => setSlug(e.target.value)}
        required
      />
      <TextField
        label="project name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <TextField
        label="description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      {errors.map((e) => (
        <InlineFinding
          key={`${e.code}:${e.message}`}
          severity="error"
          message={e.message}
        />
      ))}
      <Button variant="primary" type="submit" disabled={inFlight}>
        {inFlight ? "Creating…" : "Create project"}
      </Button>
    </form>
  );
}
