"use client";

const iconButtonClass =
  "rounded-sm p-1 text-muted transition hover:text-lime";

const svgProps = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export interface ChatHeaderProps {
  fullscreen: boolean;
  onToggleFullscreen: () => void;
  onClose: () => void;
}

/** Chat panel title bar: status dot, title, expand/shrink + close controls. */
export function ChatHeader({
  fullscreen,
  onToggleFullscreen,
  onClose,
}: ChatHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-line bg-panel px-lg py-md">
      <div className="flex items-center gap-sm">
        <span className="h-2 w-2 rounded-pill bg-lime" aria-hidden="true" />
        <h2 className="text-sm font-bold tracking-tight text-ink">
          Travel Assistant
        </h2>
      </div>
      <div className="flex items-center gap-xs">
        <button
          type="button"
          aria-label={fullscreen ? "Shrink panel" : "Expand panel"}
          aria-pressed={fullscreen}
          onClick={onToggleFullscreen}
          className={iconButtonClass}
        >
          <svg {...svgProps}>
            {fullscreen ? (
              <path d="M9 9 4 4m0 0v4m0-4h4m6 5 5-5m0 0v4m0-4h-4M9 15l-5 5m0 0v-4m0 4h4m6-5 5 5m0 0v-4m0 4h-4" />
            ) : (
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
            )}
          </svg>
        </button>
        <button
          type="button"
          aria-label="Close travel assistant"
          onClick={onClose}
          className={iconButtonClass}
        >
          <svg {...svgProps}>
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </header>
  );
}
