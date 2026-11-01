export type RuntimePhase = "checking" | "database" | "migrating" | "starting" | "ready" | "error";
export type NativeRuntimeStatus = {
  phase: RuntimePhase;
  message: string;
  error: string | null;
  origin: string | null;
  ownedBackend: boolean;
  logPath: string | null;
};

declare global {
  interface Window {
    __CHEMISTRY_DESKTOP__?: boolean;
    __TAURI__?: { core: { invoke: <T>(command: string) => Promise<T> } };
  }
}

export function isNativeDesktop() {
  return window.__CHEMISTRY_DESKTOP__ === true;
}

/** Keep the web interface limited to the native launcher's fixed commands. */
export function desktopInvoke<T>(command: "runtime_status" | "runtime_retry" | "runtime_open"): Promise<T> {
  const invoke = window.__TAURI__?.core?.invoke;
  return invoke ? invoke<T>(command) : Promise.reject(new Error("The native workspace connection is unavailable."));
}
