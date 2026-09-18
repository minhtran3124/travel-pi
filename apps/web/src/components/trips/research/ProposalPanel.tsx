"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { AlreadyShortlistedError } from "@/lib/api/errors";
import { getResearchFile } from "@/lib/api/research";
import { useAddItem, type TripItemCreate } from "@/lib/query/items";
import { useAddToShortlist } from "@/lib/query/shortlist";

/** One itinerary stop in `/plan/proposal.json` (BE `research/skills/proposal`). */
interface ProposalItinerary {
  day: number;
  time?: string;
  place_id: string;
  title: string;
  notes?: string;
}

interface Proposal {
  itinerary: ProposalItinerary[];
  shortlist: string[];
}

type ApplyState = "idle" | "pending" | "ok" | "error";

function proposalKey(runId: string, path: string) {
  return ["research", "proposal", runId, path] as const;
}

/** Coerce the raw JSON into the two lists we apply, tolerating missing keys. */
function parseProposal(raw: string): Proposal {
  const doc = JSON.parse(raw) as Record<string, unknown>;
  const itinerary = Array.isArray(doc.itinerary)
    ? (doc.itinerary as ProposalItinerary[]).filter((e) => e && e.place_id)
    : [];
  const shortlist = Array.isArray(doc.shortlist)
    ? (doc.shortlist as string[]).filter(Boolean)
    : [];
  return { itinerary, shortlist };
}

/**
 * Shows `/plan/proposal.json` and applies it to the real trip through the
 * existing REST endpoints — `POST /trips/{id}/items` per itinerary stop and the
 * shortlist add per place — one request each. This is the propose-only boundary
 * (E004): the agent only writes dossier files; the trip changes only on this
 * click. Each entry keeps its own outcome so one failure never aborts the batch.
 */
export function ProposalPanel({
  tripId,
  runId,
  files,
}: {
  tripId: string;
  runId: string;
  files: string[];
}) {
  const t = useTranslations("TripDetail.research");
  const addItem = useAddItem(tripId);
  const addToShortlist = useAddToShortlist(tripId);

  const proposalPath = useMemo(
    () => files.find((path) => path.endsWith("proposal.json")) ?? null,
    [files],
  );

  const [results, setResults] = useState<Record<string, ApplyState>>({});
  const [busy, setBusy] = useState(false);

  const proposal = useQuery({
    queryKey: proposalKey(runId, proposalPath ?? ""),
    queryFn: async () => parseProposal(await getResearchFile(runId, proposalPath!)),
    enabled: proposalPath != null,
    retry: false,
  });

  async function apply(key: string, run: () => Promise<unknown>) {
    setResults((prev) => ({ ...prev, [key]: "pending" }));
    try {
      await run();
      setResults((prev) => ({ ...prev, [key]: "ok" }));
    } catch (err) {
      // A place already on the shortlist is effectively applied, not a failure.
      const ok = err instanceof AlreadyShortlistedError;
      setResults((prev) => ({ ...prev, [key]: ok ? "ok" : "error" }));
    }
  }

  async function applyAll() {
    if (!proposal.data) return;
    setBusy(true);
    for (const [i, entry] of proposal.data.itinerary.entries()) {
      const body: TripItemCreate = {
        day: entry.day,
        kind: "place",
        status: "pending",
        title: entry.title,
        sort_order: 0,
        place_id: entry.place_id,
        start_time: entry.time ?? null,
        notes: entry.notes ?? null,
      };
      await apply(`item:${i}`, () => addItem.mutateAsync(body));
    }
    for (const [i, placeId] of proposal.data.shortlist.entries()) {
      await apply(`place:${i}`, () =>
        addToShortlist.mutateAsync({ place_id: placeId, source: "catalog" }),
      );
    }
    setBusy(false);
  }

  if (proposalPath == null) return null;

  if (proposal.isPending) {
    return (
      <div className="flex justify-center py-lg">
        <Spinner label={t("proposalHeading")} />
      </div>
    );
  }

  if (proposal.isError || !proposal.data) return null;

  const { itinerary, shortlist } = proposal.data;
  const total = itinerary.length + shortlist.length;
  const applied = Object.values(results).filter((s) => s === "ok").length;
  const done = Object.keys(results).length > 0 && !busy;

  return (
    <Card className="flex flex-col gap-sm">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <h2 className="text-sm font-bold uppercase tracking-[0.08em] text-muted">
          {t("proposalHeading")}
        </h2>
        <div className="flex items-center gap-sm">
          {done ? (
            <span role="status" className="text-sm font-bold text-ink">
              {applied}/{total}
            </span>
          ) : null}
          <Button onClick={applyAll} disabled={busy || total === 0}>
            {t("apply")}
          </Button>
        </div>
      </div>

      <ul className="flex flex-col gap-xs">
        {itinerary.map((entry, i) => (
          <ProposalRow
            key={`item:${i}`}
            label={entry.title}
            meta={[entry.day ? `D${entry.day}` : "", entry.time ?? ""]
              .filter(Boolean)
              .join(" · ")}
            state={results[`item:${i}`] ?? "idle"}
          />
        ))}
        {shortlist.map((placeId, i) => (
          <ProposalRow
            key={`place:${i}`}
            label={placeId}
            meta=""
            state={results[`place:${i}`] ?? "idle"}
          />
        ))}
      </ul>
    </Card>
  );
}

function ProposalRow({
  label,
  meta,
  state,
}: {
  label: string;
  meta: string;
  state: ApplyState;
}) {
  const mark =
    state === "ok" ? "✓" : state === "error" ? "✗" : state === "pending" ? "…" : "";
  return (
    <li className="flex items-center justify-between gap-sm rounded-sm border border-line-soft px-sm py-xs text-sm">
      <span className="min-w-0 truncate text-ink">{label}</span>
      <span className="flex shrink-0 items-center gap-sm text-muted">
        {meta ? <span className="text-xs">{meta}</span> : null}
        <span aria-hidden="true">{mark}</span>
      </span>
    </li>
  );
}
