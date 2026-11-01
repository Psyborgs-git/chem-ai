import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { commit, capability } = vi.hoisted(() => ({ commit: vi.fn(), capability: { status: "available", detail: "Installed RDKit" } }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useLazyLoadQuery: () => ({ engineCapabilities: { rdkit: capability } }), useMutation: () => [commit, false] }));
import { QuickCalculation } from "./QuickCalculation";

const completed = { id: "run-1", kind: "rdkit_descriptors", status: "succeeded", resultSummary: { structure: { canonical_smiles: "CCO", formula: "C2H6O", depiction_svg: '<svg xmlns="http://www.w3.org/2000/svg"><path d="M1 2L3 4"/></svg>' }, descriptors: { mw: 46.069, hbd: 1, hba: 1 } } };
function renderCalculator() { render(<MemoryRouter><QuickCalculation projects={[{id:"project-1",name:"Selected research"}]} /></MemoryRouter>); }
const form = () => screen.getByRole("form", { name: "Quick molecular calculation" });

describe("direct Home molecular calculation", () => {
  beforeEach(() => { commit.mockReset(); capability.status = "available"; });
  it("requires only a structure, avoids duplicate submissions, and waits for a real result", () => {
    renderCalculator();
    expect(screen.getByRole("textbox", {name:"Molecular structure"})).toHaveValue("");
    expect(screen.getByRole("button", {name:"Calculate properties"})).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", {name:"Molecular structure"}), {target:{value:" CCO "}});
    fireEvent.submit(form()); fireEvent.submit(form());
    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit.mock.calls[0][0].variables.input).toMatchObject({smiles:"CCO",projectId:null});
    expect(screen.queryByText("C2H6O")).not.toBeInTheDocument();
    act(() => commit.mock.calls[0][0].onCompleted({runs:{quickDescribeStructure:{run:completed,errors:[]}}}));
    expect(screen.getByText("C2H6O")).toBeInTheDocument();
    expect(screen.getByRole("img", {name:"Molecular structure of CCO"})).toHaveAttribute("src",expect.stringMatching(/^data:image\/svg\+xml,/));
    expect(screen.getByRole("link",{name:/Open full result/})).toHaveAttribute("href","/runs/run-1");
    fireEvent.change(screen.getByRole("textbox",{name:"Molecular structure"}),{target:{value:"O"}});
    expect(screen.queryByText("C2H6O")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
  it("preserves the uncertain request identity and entered structure on retry", () => {
    renderCalculator(); fireEvent.click(screen.getByRole("button",{name:"Try ethanol"})); fireEvent.submit(form());
    const first = commit.mock.calls[0][0]; act(() => first.onError(new Error("network")));
    expect(screen.getByRole("alert")).toHaveTextContent("Retry to check the original calculation");
    expect(screen.getByRole("textbox",{name:"Molecular structure"})).toHaveValue("CCO");
    fireEvent.submit(form()); expect(commit.mock.calls[1][0].variables.input.idempotencyKey).toBe(first.variables.input.idempotencyKey);
  });
  it("honors explicit project context and changes identity when input changes", () => {
    renderCalculator(); fireEvent.click(screen.getByText(/Save to a project/));
    fireEvent.change(screen.getByLabelText("Project"),{target:{value:"project-1"}});
    fireEvent.click(screen.getByRole("button",{name:"Try ethanol"})); fireEvent.submit(form());
    const first = commit.mock.calls[0][0]; expect(first.variables.input.projectId).toBe("project-1");
    act(() => first.onError(new Error("network")));
    fireEvent.change(screen.getByRole("textbox",{name:"Molecular structure"}),{target:{value:"O"}}); fireEvent.submit(form());
    expect(commit.mock.calls[1][0].variables.input.idempotencyKey).not.toBe(first.variables.input.idempotencyKey);
  });
  it("disables unavailable calculations without inventing a result", () => {
    capability.status="unavailable"; renderCalculator(); fireEvent.click(screen.getByRole("button",{name:"Try ethanol"})); fireEvent.submit(form());
    expect(commit).not.toHaveBeenCalled(); expect(screen.getByRole("status")).toHaveTextContent("local engine is unavailable");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
