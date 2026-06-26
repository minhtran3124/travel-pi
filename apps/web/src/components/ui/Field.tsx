import { useId } from "react";
import type { InputHTMLAttributes } from "react";

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export function Field({ label, id, className, ...props }: FieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <div className="flex flex-col gap-xs">
      <label
        htmlFor={inputId}
        className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted"
      >
        {label}
      </label>
      <input
        id={inputId}
        className={[
          "h-[34px] rounded-sm border border-line bg-panel-raised px-sm text-sm text-ink placeholder:text-muted",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...props}
      />
    </div>
  );
}
