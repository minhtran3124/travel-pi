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
      <select
        id={selectId}
        className={cn(controlClass, "h-[34px] w-full px-sm", className)}
        {...props}
      >
        {children}
      </select>
    </div>
  );
}
