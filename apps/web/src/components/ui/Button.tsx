import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type ButtonVariant = "primary" | "ghost";
type ButtonSize = "default" | "icon";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  /** `icon` makes a square 34px button for a single glyph. */
  size?: ButtonSize;
}

const base =
  "inline-flex h-[34px] items-center justify-center rounded-sm text-sm font-bold transition active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50";

const sizes: Record<ButtonSize, string> = {
  default: "px-[18px]",
  icon: "w-[34px] shrink-0",
};

const variants: Record<ButtonVariant, string> = {
  primary: "bg-ink text-on-ink hover:bg-ink-hover",
  ghost:
    "border border-line bg-panel text-ink hover:bg-panel-raised",
};

export function Button({
  variant = "primary",
  size = "default",
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(base, sizes[size], variants[variant], className)}
      {...props}
    />
  );
}
