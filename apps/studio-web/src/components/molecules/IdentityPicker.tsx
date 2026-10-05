import { useId, useState } from "react";

import { TextField } from "../atoms/TextField";

/** Identity search field — results arrive resolved from the
 * registry; this control only renders candidates with their
 * identifiers so selection is never name-only guessing (§6.2). */
export function IdentityPicker({
  label,
  candidates,
  onSelect,
}: {
  label: string;
  candidates: readonly {
    id: string;
    name: string;
    identifiers: readonly string[];
  }[];
  onSelect?: (id: string) => void;
}) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const shown = candidates.filter((c) =>
    c.name.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="cs-identity-picker">
      <TextField
        label={label}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        role="combobox"
        aria-expanded={shown.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
      />
      <ul id={listId} role="listbox" className="cs-identity-picker__list">
        {shown.map((c) => (
          <li key={c.id} role="option" aria-selected={false}>
            <button type="button" onClick={() => onSelect?.(c.id)}>
              {c.name}
              <span className="cs-identity-picker__ids">
                {" "}
                · {c.identifiers.join(", ")}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
