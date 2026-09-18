"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { FileViewer } from "@/components/trips/research/FileViewer";
import { ProposalPanel } from "@/components/trips/research/ProposalPanel";
import { useResearchStream } from "@/components/trips/research/useResearchStream";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import {
  getLatestResearch,
  reviseResearch,
  startResearch,
} from "@/lib/api/research";

/** Query key for the trip's latest-run summary (locked/empty/active gate). */
function latestKey(tripId: string) {
  return ["research", "latest", tripId] as const;
}

/**
 * The HTTP status carried by the `Error` that `lib/api/research.ts` throws
 * (`${path}: ${status}`). Lets the tab branch a 403 (not premium → locked) and
 * a 404 (no run yet, or the flag-gated router is absent → empty) apart from a
 * generic failure without a dedicated typed error.
 */
function statusOf(error: unknown): number | null {
  const message = error instanceof Error ? error.message : "";
  const match = message.match(/:\s*(\d{3})\s*$/);
  return match ? Number(match[1]) : null;
}

/** A run is worth a live stream only while it is still running. */
const RUNNING = "running";

export function ResearchTab({ tripId }: { tripId: string }) {
  const t = useTranslations("TripDetail.research");
  const locale = useLocale();
  const queryClient = useQueryClient();

  // A run this session started or revised — streamed live even before the
  // latest-summary query has refetched to see it.
  const [liveRunId, setLiveRunId] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionFailed, setActionFailed] = useState(false);
  const [openFile, setOpenFile] = useState<string | null>(null);

  const latest = useQuery({
    queryKey: latestKey(tripId),
    queryFn: () => getLatestResearch(tripId),
    retry: false,
  });

  const summary = latest.data ?? null;
  const runId = liveRunId ?? summary?.run_id ?? null;
  // Subscribe while EITHER this session started/revised a run (`liveRunId`) or
  // the latest summary still reports one running. The live stream is what tells
  // us the run finished, so keep the id even after it terminates.
  const wantsStream = liveRunId != null || summary?.status === RUNNING;
  const stream = useResearchStream(wantsStream ? runId : null);
  // A terminal stream event (done or error) leaves the running view even though
  // `liveRunId` / the stale summary still point at the run — otherwise the
  // "Researching…" card would spin forever after a completed run. Starting a
  // new run swaps `runId`, which resets the stream back to `streaming`.
  const streamSettled = stream.status === "done" || stream.status === "error";
  const isRunning = wantsStream && !streamSettled;

  const filePaths = useMemo(() => {
    const paths = new Set<string>();
    for (const path of summary?.files ?? []) paths.add(path);
    for (const file of stream.files) paths.add(file.path);
    return [...paths].sort();
  }, [summary?.files, stream.files]);

  const proposalReady = Boolean(summary?.proposal_ready) || stream.proposalReady;

  async function runAction(action: () => Promise<{ run_id: string }>) {
    setActionFailed(false);
    setBusy(true);
    try {
      const res = await action();
      setLiveRunId(res.run_id);
      setOpenFile(null);
      await queryClient.invalidateQueries({ queryKey: latestKey(tripId) });
    } catch {
      // A start against the flag-gated (absent) router 404s; surface a calm
      // notice rather than letting the rejection crash the tab.
      setActionFailed(true);
    } finally {
      setBusy(false);
    }
  }

  function handleStart() {
    void runAction(() => startResearch(tripId, { language: locale }));
  }

  function handleRevise() {
    const trimmed = instruction.trim();
    if (!runId || !trimmed) return;
    setInstruction("");
    void runAction(() => reviseResearch(runId, trimmed));
  }

  // -- Gate: pending / locked / empty / error before any run is in view -------

  if (latest.isPending && liveRunId == null) {
    return (
      <div className="flex justify-center py-xl">
        <Spinner label={t("running")} />
      </div>
    );
  }

  if (runId == null) {
    const code = latest.isError ? statusOf(latest.error) : null;

    if (code === 403) {
      return (
        <EmptyState
          icon="🔒"
          title={t("lockedTitle")}
          hint={t("lockedHint")}
          action={<Button disabled>{t("upgradeCta")}</Button>}
        />
      );
    }

    if (code === 404 || !latest.isError) {
      return (
        <section className="flex flex-col gap-md">
          <EmptyState
            icon="🧭"
            title={t("emptyTitle")}
            hint={t("emptyHint")}
            action={
              <Button onClick={handleStart} disabled={busy}>
                {busy ? t("running") : t("start")}
              </Button>
            }
          />
          {actionFailed ? <Notice>{t("error")}</Notice> : null}
        </section>
      );
    }

    return <EmptyState icon="⚠️" title={t("error")} />;
  }

  // -- Active run: progress, files, revise, proposal --------------------------

  return (
    <section className="flex flex-col gap-lg">
      {isRunning ? (
        <Card className="flex flex-col gap-sm">
          <div className="flex items-center gap-sm">
            <Spinner label={t("running")} />
            <h2 className="text-sm font-bold uppercase tracking-[0.08em] text-muted">
              {t("running")}
            </h2>
          </div>
          <Progress
            todos={stream.todos}
            subagents={stream.subagents}
            tools={stream.tools}
            lastEval={stream.lastEval}
          />
        </Card>
      ) : null}

      {stream.status === "error" ? <Notice>{t("error")}</Notice> : null}

      {filePaths.length > 0 ? (
        <section className="flex flex-col gap-sm">
          <h2 className="text-sm font-bold uppercase tracking-[0.08em] text-muted">
            {t("filesHeading")}
          </h2>
          <div className="flex flex-col gap-md md:flex-row md:items-start">
            <ul className="flex shrink-0 flex-col gap-xs md:w-[16rem]">
              {filePaths.map((path) => (
                <li key={path}>
                  <button
                    type="button"
                    onClick={() => setOpenFile(path)}
                    aria-pressed={openFile === path}
                    className={
                      "w-full truncate rounded-sm border px-sm py-xs text-left text-sm transition " +
                      (openFile === path
                        ? "border-line bg-panel-raised text-ink"
                        : "border-line-soft text-muted hover:bg-panel-raised hover:text-ink")
                    }
                  >
                    {path}
                  </button>
                </li>
              ))}
            </ul>
            <div className="min-w-0 flex-1">
              {openFile ? (
                <FileViewer runId={runId} path={openFile} />
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      {proposalReady ? (
        <ProposalPanel tripId={tripId} runId={runId} files={filePaths} />
      ) : null}

      <Card className="flex flex-col gap-sm">
        <h2 className="text-sm font-bold uppercase tracking-[0.08em] text-muted">
          {t("reviseTitle")}
        </h2>
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder={t("revisePlaceholder")}
          rows={2}
          className="w-full resize-y rounded-sm border border-line bg-panel px-sm py-xs text-sm text-ink outline-none placeholder:text-faint focus:border-faint"
        />
        <div className="flex items-center gap-sm">
          <Button
            onClick={handleRevise}
            disabled={busy || instruction.trim().length === 0}
          >
            {t("revise")}
          </Button>
          {actionFailed ? <Notice>{t("error")}</Notice> : null}
        </div>
      </Card>
    </section>
  );
}

/** A calm, non-crashing inline notice reused across the tab's error paths. */
function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="status"
      className="rounded-sm border border-line bg-panel-raised px-sm py-xs text-sm text-muted"
    >
      {children}
    </p>
  );
}

interface ProgressProps {
  todos: { content: string; status: string }[];
  subagents: { name: string; status: string }[];
  tools: { name: string; status: string }[];
  lastEval: { iteration: number; result: string; explanation: string } | null;
}

/**
 * Live progress rendered entirely from streamed values (todo text, subagent /
 * tool names, rubric verdict) — the tab holds no copy for these, so no strings
 * are invented for the projected states.
 */
function Progress({ todos, subagents, tools, lastEval }: ProgressProps) {
  const named = [...subagents, ...tools];
  return (
    <div className="flex flex-col gap-sm">
      {todos.length > 0 ? (
        <ul className="flex flex-col gap-xs">
          {todos.map((todo, i) => (
            <li key={`${todo.content}-${i}`} className="flex items-start gap-xs text-sm">
              <span aria-hidden="true" className="text-muted">
                {todo.status === "completed" ? "✓" : "•"}
              </span>
              <span
                className={
                  todo.status === "completed" ? "text-muted line-through" : "text-ink"
                }
              >
                {todo.content}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {named.length > 0 ? (
        <ul className="flex flex-wrap gap-xs">
          {named.map((entry) => (
            <li
              key={entry.name}
              className="inline-flex items-center gap-xs rounded-pill bg-panel-raised px-sm py-px text-xs font-bold text-muted ring-1 ring-line"
            >
              <span className="text-ink">{entry.name}</span>
              <span>{entry.status}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {lastEval ? (
        <p className="text-xs text-muted">
          <span className="font-bold text-ink">{lastEval.result}</span>
          {lastEval.explanation ? ` — ${lastEval.explanation}` : null}
        </p>
      ) : null}
    </div>
  );
}
