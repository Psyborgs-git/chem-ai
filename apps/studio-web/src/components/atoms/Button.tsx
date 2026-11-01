import type { ComponentProps } from "react";
import { Button as SharedButton } from "../ui/button";

type Variant = "primary" | "secondary" | "danger" | "ghost";

export function Button({
  variant = "secondary",
  ...props
}: Omit<ComponentProps<typeof SharedButton>, "variant"> & { variant?: Variant }) {
  return (
    <SharedButton
      type="button"
      {...props}
      variant={{ primary: "default", secondary: "outline", danger: "destructive", ghost: "ghost" }[variant] as "default" | "outline" | "destructive" | "ghost"}
    />
  );
}
