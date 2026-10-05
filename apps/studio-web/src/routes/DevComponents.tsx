import { useState } from "react";

import {
  EvidenceTypeLabel,
  QuantityDisplay,
  QuantityInput,
  SaveStatus,
} from "../components";

/** Dev-only component showcase — mount point for e2e accessibility
 * journeys and a living reference for the design map. Not linked
 * from the app shell. */
export function DevComponents() {
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("mass_fraction");
  const [saved, setSaved] = useState(false);
  return (
    <main className="cs-dev">
      <h1>Component reference</h1>

      <section aria-labelledby="qi-heading">
        <h2 id="qi-heading">Quantity input</h2>
        <QuantityInput
          label="solvent amount"
          value={value}
          unit={unit}
          units={["mass_fraction", "mass_percent", "kg"]}
          basis="as_supplied"
          error={
            value !== "" && Number.parseFloat(value) > 1
              ? "fraction must be within [0,1] (domain rule)"
              : undefined
          }
          onValueChange={setValue}
          onUnitChange={setUnit}
        />
        <button type="button" onClick={() => setSaved(true)}>
          Save
        </button>
        <SaveStatus state={saved ? "saved" : "unsaved"} />
      </section>

      <section aria-labelledby="ev-heading">
        <h2 id="ev-heading">Evidence vs results</h2>
        <QuantityDisplay
          value="1.24"
          unit="Pa_s"
          basis="as_supplied"
          uncertainty="0.05"
          conditions="25 degC, 1 bar"
          evidence="predicted"
        />
        <br />
        <QuantityDisplay
          value="1.31"
          unit="Pa_s"
          basis="as_supplied"
          uncertainty="0.02"
          conditions="25 degC, 1 bar"
          evidence="measured"
        />
        <br />
        <QuantityDisplay unit="Pa_s" evidence="computed" />
        <p>
          <EvidenceTypeLabel kind="imported" /> reference label
        </p>
      </section>
    </main>
  );
}
