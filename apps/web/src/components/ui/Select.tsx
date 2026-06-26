import { useId } from "react";
import type { SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import { controlClass, labelClass } from "./control";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  /** Classes for the wrapper — use this for layout/sizing (e.g. flex-1) so the
   * outer flex item grows. `className` targets the <select> itself. */
  wrapperClassName?: string;
}

/** Labelled `<select>` mirroring {@link Field}'s chrome. */
export function Select({
  label,
  id,
  className,
  wrapperClassName,
  children,
  ...props
}: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  return (
    <div className={cn("flex min-w-0 flex-col gap-xs", wrapperClassName)}>
      <label htmlFor={selectId} className={labelClass}>
        {label}
      </label>
      {/* The select's native OS arrow is stripped in globals.css; this relative
       * wrapper hangs our own hairline chevron in the reserved right padding. */}
      <div className="relative">
        <select
          id={selectId}
          className={cn(
            controlClass,
            "h-[34px] w-full cursor-pointer appearance-none pl-sm pr-8",
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted" />
      </div>
    </div>
  );
}

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}
