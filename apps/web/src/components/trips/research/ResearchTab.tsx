"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { ProgressStepper } from "@/components/trips/research/ProgressStepper";
import { ResearchPlan } from "@/components/trips/research/ResearchPlan";
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
  // Flights need a departure point the trip does not hold: ask, never assume.
  const [origin, setOrigin] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionFailed, setActionFailed] = useState(false);

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
  // A run in view that ended without completing: the backend reports `failed` or
  // (a `running` row no longer live on the bus) `interrupted`, and a live stream
  // that errored is treated the same. The dossier stays readable, but Apply is
  // hidden and the traveller is offered a re-run.
  const unfinished: "failed" | "interrupted" | null = isRunning
    ? null
    : summary?.status === "interrupted"
      ? "interrupted"
      : summary?.status === "failed" || stream.status === "error"
        ? "failed"
        : null;

  // Once a live stream settles, the latest-summary query still holds the pre-run
  // (or "running") snapshot; refetch it so the plan view reflects the finished run.
  useEffect(() => {
    if (streamSettled) {
      void queryClient.invalidateQueries({ queryKey: latestKey(tripId) });
    }
  }, [streamSettled, tripId, queryClient]);

  const filePaths = useMemo(() => {
    const paths = new Set<string>();
    for (const path of summary?.files ?? []) paths.add(path);
    for (const file of stream.files) paths.add(file.path);
    return [...paths].sort();
  }, [summary?.files, stream.files]);

  async function runAction(action: () => Promise<{ run_id: string }>) {
    setActionFailed(false);
    setBusy(true);
    try {
      const res = await action();
      setLiveRunId(res.run_id);
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
    const trimmed = origin.trim();
    if (!trimmed) return;
    void runAction(() =>
      startResearch(tripId, { language: locale, origin: trimmed }),
    );
  }

  function handleRevise() {
    const trimmed = instruction.trim();
    if (!runId || !trimmed) return;
    setInstruction("");
    void runAction(() => reviseResearch(runId, trimmed, locale));
  }

  function handleRunAgain() {
    if (!runId) return;
    void runAction(() => reviseResearch(runId, t("resumeInstruction"), locale));
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
              <form
                className="flex w-full max-w-[22rem] flex-col items-stretch gap-sm"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleStart();
                }}
              >
                <label className="flex flex-col gap-xs text-left text-sm font-medium text-ink">
                  {t("originLabel")}
                  <input
                    value={origin}
                    onChange={(e) => setOrigin(e.target.value)}
                    placeholder={t("originPlaceholder")}
                    maxLength={120}
                    className="w-full rounded-sm border border-line bg-panel px-sm py-xs text-sm font-normal text-ink outline-none placeholder:text-faint focus:border-faint"
                  />
                </label>
                <Button type="submit" disabled={busy || origin.trim().length === 0}>
                  {busy ? t("running") : t("start")}
                </Button>
              </form>
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
          <ProgressStepper
            subagents={stream.subagents}
            files={stream.files}
            lastEval={stream.lastEval}
          />
        </Card>
      ) : (
        <>
          {unfinished ? (
            <Card className="flex flex-col gap-sm">
              <div className="flex items-start gap-sm">
                <span
                  aria-hidden="true"
                  className="grid size-6 shrink-0 place-items-center rounded-pill bg-status-estimated text-on-accent text-sm font-bold"
                >
                  !
                </span>
                <div className="flex flex-col gap-xs">
                  <h2 className="pt-[2px] text-base font-bold text-ink">
                    {t("unfinishedTitle")}
                  </h2>
                  <p className="text-sm text-muted">
                    {unfinished === "interrupted"
                      ? t("interruptedHint")
                      : t("failedHint")}
                  </p>
                </div>
              </div>
              <div>
                <Button onClick={handleRunAgain} disabled={busy}>
                  {busy ? t("running") : t("runAgain")}
                </Button>
              </div>
            </Card>
          ) : null}
          <ResearchPlan
            tripId={tripId}
            runId={runId}
            files={filePaths}
            review={summary?.review ?? null}
            applyEnabled={unfinished == null}
          />
        </>
      )}

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
        <ul className="flex flex-wrap gap-xs">
          {REVISE_CHIPS.map((key) => (
            <li key={key}>
              <button
                type="button"
                onClick={() => setInstruction(t(`reviseChips.${key}`))}
                className="rounded-pill border border-line bg-panel px-sm py-[2px] text-xs text-ink transition hover:bg-panel-raised"
              >
                {t(`reviseChips.${key}`)}
              </button>
            </li>
          ))}
        </ul>
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

/** Quick-instruction chips that prefill the revise box (localized). */
const REVISE_CHIPS = ["cheaper", "localFood", "relaxed"] as const;

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
