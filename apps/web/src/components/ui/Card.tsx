import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export type CardProps = HTMLAttributes<HTMLDivElement>;

const base =
  "rounded-md bg-panel p-lg shadow-card transition hover:-translate-y-0.5 hover:shadow-lift";

export function Card({ className, ...props }: CardProps) {
  return <div className={cn(base, className)} {...props} />;
}
