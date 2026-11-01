import { DesktopTitlebar, NativeBoot } from "./features/desktop/NativeBoot";
import { isNativeDesktop } from "./features/desktop/runtime";
import { AppRoutes } from "./routes/AppRoutes";

export function App() {
  const desktop = isNativeDesktop();
  const boot = desktop && new URLSearchParams(window.location.search).get("desktop") === "boot";
  return <>{desktop && <DesktopTitlebar />}{boot ? <NativeBoot /> : <AppRoutes />}</>;
}
