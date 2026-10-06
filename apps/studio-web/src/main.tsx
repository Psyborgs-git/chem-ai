import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { readTheme } from "./theme";
import "./styles/tokens.css";
import "./styles/components.css";

// Light/dark share the same semantic tokens (§22.5). The stored
// choice wins; otherwise follow the OS preference on first load.
document.documentElement.dataset.theme =
  readTheme() ??
  (globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light");

const container = document.getElementById("root");
if (!container) {
  throw new Error("root element missing");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
