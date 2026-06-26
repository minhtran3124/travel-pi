import { useId } from "react";
import type { SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import { controlClass, labelClass } from "./control";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
}

/** Labelled `<select>` mirroring {@link Field}'s chrome. */
export function Select({
  label,
  id,
  className,
  children,
  ...props
}: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  return (
    <div className="flex flex-col gap-xs">
      <label htmlFor={selectId} className={labelClass}>
        {label}
      </label>
      <select
        id={selectId}
        className={cn(controlClass, "h-[34px] px-sm", className)}
        {...props}
      >
        {children}
      </select>
    </div>
  );
}
