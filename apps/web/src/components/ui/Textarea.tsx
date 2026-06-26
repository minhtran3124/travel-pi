import { useId } from "react";
import type { TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import { controlClass, labelClass } from "./control";

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
}

/** Labelled `<textarea>` mirroring {@link Field}'s chrome. */
export function Textarea({ label, id, className, ...props }: TextareaProps) {
  const generatedId = useId();
  const textareaId = id ?? generatedId;
  return (
    <div className="flex flex-col gap-xs">
      <label htmlFor={textareaId} className={labelClass}>
        {label}
      </label>
      <textarea
        id={textareaId}
        // resize-y keeps the macOS corner grip from dragging the field
        // sideways and breaking the column layout — vertical growth only.
        className={cn(controlClass, "min-h-[64px] resize-y px-sm py-xs", className)}
        {...props}
      />
    </div>
  );
}
