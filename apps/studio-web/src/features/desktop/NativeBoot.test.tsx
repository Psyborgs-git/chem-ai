import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("./runtime", () => ({ desktopInvoke: invoke }));
import { NativeBoot } from "./NativeBoot";
import type { NativeRuntimeStatus } from "./runtime";

const status = (phase: NativeRuntimeStatus["phase"], message: string): NativeRuntimeStatus => ({phase,message,error:null,origin:null,ownedBackend:false,logPath:null});

describe("native startup follows the actual runtime", () => {
  beforeEach(() => { invoke.mockReset(); });
  it("marks only earlier real startup stages complete and does not open a pending service", async () => {
    invoke.mockResolvedValue(status("starting", "Opening the local research service…"));
    const {container} = render(<NativeBoot />);
    await screen.findByText("Opening the local research service…");
    expect(container.querySelectorAll('[data-state="complete"]')).toHaveLength(3);
    expect(screen.getByRole("list",{name:"Workspace startup"}).querySelector('[aria-current="step"]')).toHaveTextContent("Open Studio");
    expect(invoke).not.toHaveBeenCalledWith("runtime_open");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
  it("opens the verified workspace only after the native runtime reports ready", async () => {
    invoke.mockImplementation((command: string) => Promise.resolve(command === "runtime_status" ? {...status("ready","Your local workspace is ready."), origin:"http://127.0.0.1:8788"} : undefined));
    render(<NativeBoot />);
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("runtime_open"));
    expect(invoke.mock.calls.filter(([command]) => command === "runtime_open")).toHaveLength(1);
    expect(screen.getByRole("heading",{name:"Your workspace is ready"})).toBeInTheDocument();
  });
  it("retains an honest startup error and allows an explicit retry", async () => {
    let reads=0;
    invoke.mockImplementation((command: string) => Promise.resolve(command === "runtime_status" ? reads++ === 0 ? {...status("error","Docker Desktop needs to finish starting."),error:"Local database is unavailable",logPath:"/local/startup.log"} : status("ready","Connected.") : undefined));
    render(<NativeBoot />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Docker Desktop needs to finish starting");
    expect(invoke).not.toHaveBeenCalledWith("runtime_open");
    fireEvent.click(screen.getByRole("button",{name:"Try again"}));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("runtime_retry"));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("runtime_open"));
  });
  it("does not navigate after its window has been removed", async () => {
    let resolve!: (value: NativeRuntimeStatus) => void;
    invoke.mockReturnValue(new Promise<NativeRuntimeStatus>((done) => {resolve=done;}));
    const view=render(<NativeBoot />);
    view.unmount();
    await act(async () => {resolve(status("ready","Ready."));});
    expect(invoke).not.toHaveBeenCalledWith("runtime_open");
  });
});
