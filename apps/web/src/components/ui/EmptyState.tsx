import type { ReactNode } from "react";

export interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, hint, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-sm py-xl text-center">
      <div className="text-3xl" aria-hidden="true">
        {icon}
      </div>
      <p className="text-[1.1rem] font-extrabold text-ink">{title}</p>
      {hint ? <p className="text-sm text-muted">{hint}</p> : null}
      {action ? <div className="mt-sm">{action}</div> : null}
    </div>
  );
}
