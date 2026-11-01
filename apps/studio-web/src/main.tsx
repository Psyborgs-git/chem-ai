import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { isNativeDesktop } from "./features/desktop/runtime";
import { readTheme } from "./theme";
import { TooltipProvider } from "./components/ui/tooltip";
import "./styles/tokens.css";
import "./styles/components.css";
import "./styles/product.css";
import "./styles/motion.css";
import "./styles/shadcn.css";

// The research studio starts light; an explicit saved choice wins.
document.documentElement.dataset.theme =
  readTheme() ?? "light";

document.documentElement.classList.toggle("cs-desktop", isNativeDesktop());

const container = document.getElementById("root");
if (!container) {
  throw new Error("root element missing");
}

createRoot(container).render(
  <StrictMode>
    <TooltipProvider><App /></TooltipProvider>
  </StrictMode>,
);
