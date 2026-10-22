"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { AssistantMarkdown } from "@/components/chat/AssistantMarkdown";
import { getResearchFile } from "@/lib/api/research";

/** Query key for one dossier file's content (shared with FileViewer's family). */
function fileKey(runId: string, path: string) {
  return ["research", "file", runId, path] as const;
}

/**
 * Read-only prose for one dossier file — the section fallback when the proposal
 * carries no structured ids for it (or a lookup failed). A missing/empty file
 * renders nothing rather than an error, so a section never blanks the tab.
 */
export function FileProse({ runId, path }: { runId: string; path: string }) {
  const t = useTranslations("Common");
  const content = useQuery({
    queryKey: fileKey(runId, path),
    queryFn: () => getResearchFile(runId, path),
    retry: false,
  });

  if (content.isPending) {
    return <div className="h-16 animate-pulse rounded-sm bg-panel-raised" aria-label={t("loading")} />;
  }
  const text = content.data?.trim();
  if (content.isError || !text) return null;
  return <AssistantMarkdown content={text} isStreaming={false} />;
}
