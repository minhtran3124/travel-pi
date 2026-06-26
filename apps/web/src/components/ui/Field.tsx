import { useId } from "react";
import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import { controlClass, labelClass } from "./control";

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  /** Classes for the wrapper — use this for layout/sizing (e.g. flex-1) so the
   * outer flex item grows. `className` targets the <input> itself. */
  wrapperClassName?: string;
}

export function Field({
  label,
  id,
  className,
  wrapperClassName,
  ...props
}: FieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <div className={cn("flex min-w-0 flex-col gap-xs", wrapperClassName)}>
      <label htmlFor={inputId} className={labelClass}>
        {label}
      </label>
      <input
        id={inputId}
        className={cn(controlClass, "h-[34px] w-full px-sm", className)}
        // Suppress password-manager / autofill overlays. These inject an inline
        // button into the field (e.g. on "Name"-labelled inputs) that inflates
        // its height and breaks row alignment. No Field here is a credential
        // input, so suppression is always safe. Caller props below can override.
        autoComplete="off"
        data-1p-ignore=""
        data-lpignore="true"
        data-bwignore="true"
        data-form-type="other"
        data-protonpass-ignore="true"
        {...props}
      />
    </div>
  );
}
