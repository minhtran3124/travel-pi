import type { ReactNode } from "react";

export interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, hint, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-md py-xl text-center">
      <div
        aria-hidden="true"
        className="grid size-16 place-items-center rounded-pill bg-panel-raised text-3xl ring-1 ring-line"
      >
        {icon}
      </div>
      <div className="flex flex-col gap-xs">
        <p className="text-[1.15rem] font-extrabold text-ink">{title}</p>
        {hint ? (
          <p className="mx-auto max-w-[44ch] text-sm text-muted">{hint}</p>
        ) : null}
      </div>
      {action ? <div className="mt-xs">{action}</div> : null}
    </div>
  );
}
