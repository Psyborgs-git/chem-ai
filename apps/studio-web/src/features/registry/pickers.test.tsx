import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ twoCandidates: false, twoContracts: false }));

vi.mock("react-relay", () => ({
  graphql: () => ({}),
  useLazyLoadQuery: () => ({ taskCandidateRevisions: { edges: [{ node: {
    id: btoa("CandidateRevision:candidate-1"), revision: 1,
    entityKind: "formulation", status: "accepted_for_research", hypothesis: "Ethanol baseline",
  } }, ...(state.twoCandidates ? [{ node: { id: btoa("CandidateRevision:candidate-2"), revision: 2, entityKind: "formulation", status: "accepted_for_research", hypothesis: "Second candidate" } }] : [])] },
  taskContractRevisions: { edges: [{ node: { id: btoa("ContractRevision:contract-1"), revision: 1, status: "frozen" } }, ...(state.twoContracts ? [{ node: { id: btoa("ContractRevision:contract-2"), revision: 2, status: "frozen" } }] : [])] } }),
}));
import { CandidateRevisionPicker, ContractRevisionPicker } from "./pickers";

function Form({ automatic = false, contract = false }: { automatic?: boolean; contract?: boolean }) {
  const [id, setId] = useState("");
  const Picker = contract ? ContractRevisionPicker : CandidateRevisionPicker;
  return <><Picker taskId="task-1" selectedId={id} autoSelectSingle={automatic}
    onPick={(p) => setId(p.uuid)} onClear={() => setId("")} />
    <output aria-label="saved revision">{id || "unbound"}</output>
    <button onClick={() => setId("")}>Save and reset</button></>;
}

describe("controlled registry selection", () => {
  beforeEach(() => { state.twoCandidates = false; state.twoContracts = false; });
  it("clears the parent binding when the user changes selection", () => {
    render(<Form />);
    fireEvent.click(screen.getByRole("button", { name: /formulation candidate rev 1/ }));
    expect(screen.getByLabelText("saved revision")).toHaveTextContent("candidate-1");
    fireEvent.click(screen.getByRole("button", { name: "change" }));
    expect(screen.getByLabelText("saved revision")).toHaveTextContent("unbound");
    expect(screen.getByRole("button", { name: /formulation candidate rev 1/ })).toBeVisible();
  });
  it("drops stale labels after a form reset and allows another selection", () => {
    render(<Form />);
    fireEvent.click(screen.getByRole("button", { name: /formulation candidate rev 1/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save and reset" }));
    expect(screen.queryByText("selected:")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /formulation candidate rev 1/ }));
    expect(screen.getByLabelText("saved revision")).toHaveTextContent("candidate-1");
  });
  it("uses the sole accepted candidate once and respects an explicit clear", async () => {
    render(<Form automatic />);
    await waitFor(() => expect(screen.getByLabelText("saved revision")).toHaveTextContent("candidate-1"));
    fireEvent.click(screen.getByRole("button", { name: "change" }));
    expect(screen.getByLabelText("saved revision")).toHaveTextContent("unbound");
    fireEvent.click(screen.getByRole("button", { name: "Save and reset" }));
    expect(screen.getByLabelText("saved revision")).toHaveTextContent("unbound");
  });
  it("does not guess between accepted candidates", () => {
    state.twoCandidates = true;
    render(<Form automatic />);
    expect(screen.getByLabelText("saved revision")).toHaveTextContent("unbound");
  });
  it("uses one frozen contract but never guesses between frozen revisions", async () => {
    const first = render(<Form automatic contract />);
    await waitFor(() => expect(screen.getByLabelText("saved revision")).toHaveTextContent("contract-1"));
    first.unmount();
    state.twoContracts = true;
    render(<Form automatic contract />);
    expect(screen.getByLabelText("saved revision")).toHaveTextContent("unbound");
  });
});
