import type { ComponentProps, ReactNode } from "react";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";

type IconButtonProps = Omit<ComponentProps<typeof Button>, "aria-label" | "size" | "children"> & {
  label: string;
  children: ReactNode;
};

/** Recognizable toolbar actions keep an accessible name and keyboard tooltip. */
export function IconButton({ label, children, variant = "ghost", className = "", type = "button", ...props }: IconButtonProps) {
  return <TooltipProvider delayDuration={450}><Tooltip><TooltipTrigger asChild><Button {...props} type={type} variant={variant} size="icon" aria-label={label} data-icon-only className={`cs-icon-btn cs-icon-button ${className}`}><span aria-hidden="true">{children}</span></Button></TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip></TooltipProvider>;
}
