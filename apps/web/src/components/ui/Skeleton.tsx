import { cn } from "@/lib/cn";

export interface SkeletonProps {
  className?: string;
}

/** Block placeholder primitive for loading states. */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div className={cn("animate-pulse rounded-sm bg-panel-raised", className)} />
  );
}
