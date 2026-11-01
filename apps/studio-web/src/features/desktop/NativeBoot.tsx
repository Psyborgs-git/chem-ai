import { useEffect, useRef, useState } from "react";
import { BrandMark } from "../../components/layout/BrandMark";
import { ChemistryArt } from "../../components/layout/ChemistryArt";
import { Button } from "../../components/atoms/Button";
import { desktopInvoke, type NativeRuntimeStatus, type RuntimePhase } from "./runtime";

const STAGES: { phase: RuntimePhase; label: string; detail: string }[] = [
  { phase: "checking", label: "Workspace", detail: "Finding your local installation" },
  { phase: "database", label: "Research library", detail: "Connecting to your saved research" },
  { phase: "migrating", label: "Prepare", detail: "Checking the workspace format" },
  { phase: "starting", label: "Open Studio", detail: "Starting your local research services" },
];

const INITIAL: NativeRuntimeStatus = { phase: "checking", message: "Preparing your workspace…", error: null, origin: null, ownedBackend: false, logPath: null };

export function DesktopTitlebar() {
  return <div className="cs-desktop-titlebar" data-tauri-drag-region><span data-tauri-drag-region>Chemistry Studio</span><span className="cs-desktop-titlebar__detail" data-tauri-drag-region>Research, connected.</span></div>;
}

export function NativeBoot() {
  const [status, setStatus] = useState<NativeRuntimeStatus>(INITIAL);
  const [attempt, setAttempt] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const opening = useRef(false);
  const stageIndex = status.phase === "ready" ? STAGES.length : STAGES.findIndex((stage) => stage.phase === status.phase);
  const failed = status.phase === "error";
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await desktopInvoke<NativeRuntimeStatus>("runtime_status");
        if (disposed) return;
        setStatus(next);
        if (next.phase === "ready" && !opening.current) {
          opening.current = true;
          try { await desktopInvoke<void>("runtime_open"); }
          catch (error) {
            opening.current = false;
            if (!disposed) setStatus({ ...next, phase: "error", message: "Your workspace is ready, but its window could not open.", error: String(error) });
          }
          return;
        }
        if (next.phase !== "error") timer = setTimeout(() => { void poll(); }, 400);
      } catch (error) {
        if (!disposed) setStatus({ ...INITIAL, phase: "error", message: "The native workspace connection could not start.", error: String(error) });
      }
    };
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [attempt]);
  const retry = async () => {
    if (retrying) return;
    setRetrying(true);
    opening.current = false;
    try {
      await desktopInvoke("runtime_retry");
      setStatus(INITIAL);
      setAttempt((value) => value + 1);
    } catch (error) { setStatus((current) => ({ ...current, phase: "error", message: "The workspace could not restart.", error: String(error) })); }
    finally { setRetrying(false); }
  };
  return <main className={`cs-native-launcher${failed ? " is-error" : ""}`}>
    <div className="cs-native-launcher__ambient" aria-hidden="true"><span/><span/><span/></div>
    <div className="cs-native-launcher__brand"><BrandMark size={44}/><span>Chemistry Studio</span></div>
    <div className="cs-native-launcher__layout">
      <section className="cs-native-launcher__story"><p className="cs-kicker">A home for your research</p><h1>Good questions.<br/><span>New possibilities.</span></h1><p>From a molecular structure to a considered decision. Your research, in one connected workspace.</p><div className="cs-native-launcher__art"><ChemistryArt kind="research"/><span className="cs-launch-orbit cs-launch-orbit--one"/><span className="cs-launch-orbit cs-launch-orbit--two"/></div></section>
      <section className="cs-native-launcher__status" aria-labelledby="native-launch-title"><div className="cs-native-launcher__symbol"><BrandMark size={76}/></div><p className="cs-kicker">Your local studio</p><h2 id="native-launch-title">{failed ? "Let’s get you connected" : status.phase === "ready" ? "Your workspace is ready" : "Making room for discovery"}</h2><p className="cs-native-launcher__message" role={failed ? "alert" : "status"} aria-live="polite">{status.message}</p>
        <ol className="cs-launch-stages" aria-label="Workspace startup">{STAGES.map((stage, index) => <li key={stage.phase} data-state={index < stageIndex ? "complete" : index === stageIndex ? "current" : "waiting"} aria-current={index === stageIndex ? "step" : undefined}><span className="cs-launch-stage-symbol" aria-hidden="true">{index < stageIndex ? "✓" : `0${index + 1}`}</span><span><strong>{stage.label}</strong><small>{stage.detail}</small></span>{index === stageIndex && <span className="cs-launch-stage-pulse" aria-hidden="true"/>}</li>)}</ol>
        {failed && <div className="cs-launch-recovery"><Button variant="primary" onClick={() => { void retry(); }} disabled={retrying}>{retrying ? "Reconnecting…" : "Try again"}</Button><details><summary>Startup details</summary>{status.error && <p>{status.error}</p>}{status.logPath && <p>Local log: <code>{status.logPath}</code></p>}</details></div>}
        <div className="cs-native-launcher__footnote"><span aria-hidden="true">⌘</span> Made for your Mac. Built around your research.</div>
      </section>
    </div>
    <footer className="cs-native-launcher__footer"><span>Explore · Experiment · Understand</span><span>Chemistry Studio for macOS</span></footer>
  </main>;
}
