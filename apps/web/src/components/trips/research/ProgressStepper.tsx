"use client";

import { useTranslations } from "next-intl";

import type {
  NamedStatus,
  ResearchEvalState,
  ResearchFile,
} from "./useResearchStream";

// The dossier's specialists in reading order. A step is done once its dimension
// file is written — the stream reliably carries `research_file` paths — or its
// subagent reports finished; the "quality" step is the rubric verdict. Copy is
// localized; a raw subagent/tool name or the grader's explanation is NEVER rendered.
const STEPS: ReadonlyArray<{
  key: string;
  agent: string | null;
  file: RegExp | null;
  icon: string;
}> = [
  { key: "flights", agent: "flights", file: /\/flights\.md$/, icon: "✈" },
  { key: "stays", agent: "stays", file: /\/stays\.md$/, icon: "🏨" },
  { key: "days", agent: "days", file: /\/days\/day-\d+\.md$/, icon: "📅" },
  { key: "budget", agent: "budget", file: /\/budget\.md$/, icon: "💰" },
  { key: "entry", agent: "entry_season", file: /\/entry-and-season\.md$/, icon: "🛂" },
  { key: "quality", agent: null, file: null, icon: "✓" },
];

type StepState = "pending" | "active" | "done";

/** A subagent status reads as finished — tolerant of the backend's vocabulary. */
function isDone(status: string): boolean {
  return /ok|done|complete|success|finish|pass|end/i.test(status);
}

function isStepDone(
  step: (typeof STEPS)[number],
  subagents: NamedStatus[],
  files: ResearchFile[],
  lastEval: ResearchEvalState | null,
): boolean {
  if (step.agent === null) return lastEval !== null;
  if (step.file && files.some((f) => step.file!.test(f.path))) return true;
  const found = subagents.find((s) => s.name === step.agent);
  return found !== undefined && isDone(found.status);
}

/**
 * Friendly, localized progress for a running research run. Derived only from the
 * streamed subagent names and the rubric verdict — no tool names, ids, or grader
 * text ever reach the DOM.
 */
export function ProgressStepper({
  subagents,
  files = [],
  lastEval,
}: {
  subagents: NamedStatus[];
  files?: ResearchFile[];
  lastEval: ResearchEvalState | null;
}) {
  const t = useTranslations("TripDetail.research");
  const done = STEPS.map((step) => isStepDone(step, subagents, files, lastEval));
  // The first unfinished step is the one being worked on.
  const active = done.indexOf(false);
  return (
    <ul className="flex flex-col gap-xs">
      {STEPS.map(({ key, icon }, i) => {
        const state: StepState = done[i] ? "done" : i === active ? "active" : "pending";
        const mark = state === "done" ? "✓" : state === "active" ? "●" : "○";
        return (
          <li key={key} data-state={state} className="flex items-center gap-sm text-sm">
            <span aria-hidden="true" className="w-5 text-center">
              {icon}
            </span>
            <span
              className={
                state === "pending" ? "flex-1 text-muted" : "flex-1 text-ink"
              }
            >
              {t(`progress.${key}`)}
            </span>
            <span
              aria-hidden="true"
              className={state === "done" ? "text-lime" : "text-muted"}
            >
              {mark}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
