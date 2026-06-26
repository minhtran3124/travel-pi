import { useId } from "react";
import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import { controlClass, labelClass } from "./control";

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export function Field({ label, id, className, ...props }: FieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <div className="flex flex-col gap-xs">
      <label htmlFor={inputId} className={labelClass}>
        {label}
      </label>
      <input
        id={inputId}
        className={cn(controlClass, "h-[34px] px-sm", className)}
        {...props}
      />
    </div>
  );
}
