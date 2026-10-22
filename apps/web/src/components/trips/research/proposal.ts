"use client";

import { useQuery } from "@tanstack/react-query";

import { getResearchFile } from "@/lib/api/research";

/** One itinerary stop in `/plan/proposal.json` (BE `research/skills/proposal`). */
export interface ProposalItinerary {
  day: number;
  time?: string;
  place_id: string;
  title: string;
  notes?: string;
}

/** The structured proposal, coerced so any list may be empty and missing. */
export interface Proposal {
  itinerary: ProposalItinerary[];
  shortlist: string[];
  flights: string[];
  hotels: string[];
  budgetEstimate: number | null;
}

/** Locate the proposal file in a run's file index (path may carry a prefix). */
export function proposalPathOf(files: string[]): string | null {
  return files.find((path) => path.endsWith("proposal.json")) ?? null;
}

/** Coerce the raw JSON into the lists we render, tolerating missing keys. */
export function parseProposal(raw: string): Proposal {
  const doc = JSON.parse(raw) as Record<string, unknown>;
  const itinerary = Array.isArray(doc.itinerary)
    ? (doc.itinerary as ProposalItinerary[]).filter((e) => e && e.place_id)
    : [];
  const asIds = (value: unknown): string[] =>
    Array.isArray(value) ? (value as unknown[]).map(String).filter(Boolean) : [];
  const estimate =
    typeof doc.budget_estimate === "number" && Number.isFinite(doc.budget_estimate)
      ? doc.budget_estimate
      : null;
  return {
    itinerary,
    shortlist: asIds(doc.shortlist),
    flights: asIds(doc.flights),
    hotels: asIds(doc.hotels),
    budgetEstimate: estimate,
  };
}

function proposalKey(runId: string, path: string) {
  return ["research", "proposal", runId, path] as const;
}

/**
 * Fetch and parse `/plan/proposal.json`. Disabled (and `data` stays undefined)
 * when the run wrote no proposal, so callers fall back to the dossier prose.
 */
export function useProposal(runId: string, files: string[]) {
  const path = proposalPathOf(files);
  return useQuery({
    queryKey: proposalKey(runId, path ?? ""),
    enabled: path != null,
    retry: false,
    queryFn: async () => parseProposal(await getResearchFile(runId, path!)),
  });
}
