"use client";

import { useManifest } from "@/lib/query/agent";

export interface QuickRepliesProps {
  onPick: (text: string) => void;
  disabled?: boolean;
}

/**
 * Quick-reply chips sourced from the agent manifest's tool names. Degrades
 * silently (renders nothing) when the manifest is unavailable.
 */
export function QuickReplies({ onPick, disabled }: QuickRepliesProps) {
  const { data } = useManifest();
  const tools = data?.tools ?? [];
  if (tools.length === 0) return null;

  // Surface a handful of read-only tools as conversation starters.
  const chips = tools
    .filter((t) => t.read_only && !t.destructive)
    .slice(0, 6);
  const source = chips.length > 0 ? chips : tools.slice(0, 6);

  return (
    <div className="flex flex-wrap gap-sm px-lg pb-sm">
      {source.map((tool) => (
        <button
          key={tool.name}
          type="button"
          disabled={disabled}
          title={tool.description}
          onClick={() => onPick(tool.name.replace(/_/g, " "))}
          className="rounded-pill border border-lime/40 bg-transparent px-md py-xs text-xs font-medium text-lime transition hover:bg-lime/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {tool.name.replace(/_/g, " ")}
        </button>
      ))}
    </div>
  );
}
