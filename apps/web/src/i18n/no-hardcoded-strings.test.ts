import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Positive-control gate against hardcoded (non-translated) UI strings.
 *
 * Two independent detectors, each proven against three assertions of its own
 * (scanned-file count > 0, zero real violations, exactly one violation on an
 * inline known-bad fixture) — see specs/review-c3-web-ssr-i18n/PLAN.md Task 6.1.
 * A single test-wide file count is not enough: detector 1's `src/` scan alone
 * would satisfy it even if detector 2's narrower glob resolved to nothing.
 */

const SRC_ROOT = join(__dirname, "..");

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      walk(full, out);
    } else if (/\.(tsx|ts)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

function toPosixRelative(path: string): string {
  return relative(SRC_ROOT, path).split("\\").join("/");
}

// --- Detector 1: bare-string aria-label="…" -------------------------------

const ARIA_LABEL_LITERAL_RE = /aria-label\s*=\s*"[^"]*"/g;

function ariaLabelViolations(source: string): string[] {
  return source.match(ARIA_LABEL_LITERAL_RE) ?? [];
}

function isAriaLabelScanned(relPath: string): boolean {
  if (relPath.startsWith("app/auth/")) return false; // owned by auth-pages-redesign
  if (relPath === "components/chat/AgentAvatar.tsx") return false; // brand name
  if (relPath.includes(".test.")) return false; // fixture selectors, correct as-is
  return true;
}

// --- Detector 2: bare English visible JSX text ----------------------------

// Text strictly between `>` and `<` with no interpolation braces in between,
// containing at least one letter — i.e. a literal JSX text child, not a
// `{t("key")}` expression or an aria-hidden icon's whitespace-only gap.
//
// Known limit, not a defect: any node containing a brace is skipped whole, so
// a mixed node like `<p>Signed in as {name}</p>` is not detected — the same
// rule that lets `{t("key")}` through also lets untranslated text sharing a
// node with an expression through.
const JSX_TEXT_RE = />([^<>{}]*[A-Za-z][^<>{}]*)</g;

// A TS generic argument list (`useState<string | null>`, `useRef<HTMLDivElement>`)
// always has a word character directly before its `<`, with no separator — a
// JSX opening tag never does (it's preceded by `(`, whitespace, `>`, `{`, or a
// newline). The negative lookahead keeps a text node ending right before a
// closing tag (`out</span>`) from being mistaken for one. Strip generics first
// so their `<...>` isn't mistaken for a JSX tag pair.
const TS_GENERIC_RE = /\w<(?!\/)[^<>]*>/g;

function jsxTextViolations(source: string): string[] {
  const withoutGenerics = source.replace(TS_GENERIC_RE, (m) => " ".repeat(m.length));
  const matches: string[] = [];
  for (const m of withoutGenerics.matchAll(JSX_TEXT_RE)) {
    const text = m[1].trim();
    if (text.length > 0) matches.push(text);
  }
  return matches;
}

// Scope is deliberately narrow: `components/app-shell/**` plus
// `UserMenu.tsx` only, NOT the rest of `components/auth/`. That directory
// (AuthHero.tsx, OAuthButtons.tsx, SignOutButton.tsx, ...) is the auth
// surface owned by a different spec, currently blocked behind an Auth hard
// gate that this slice must not touch — widening the glob there would fire
// the gate on files this slice deliberately excludes.
//
// Known gap this leaves uncovered: `SignOutButton.tsx` has a bare "Sign out"
// JSX text node (detector 2's exact target class) and is not scanned. It is
// verified dead code (zero importers), so nothing untranslated renders today
// — but a future reader must not read this narrow scope as full coverage of
// `components/auth/`.
function isJsxTextScanned(relPath: string): boolean {
  return (
    relPath.startsWith("components/app-shell/") ||
    relPath === "components/auth/UserMenu.tsx"
  );
}

describe("hardcoded-string gate", () => {
  const allFiles = walk(SRC_ROOT);

  it("detector 1 (aria-label): scans a non-empty set of files", () => {
    const scanned = allFiles.filter((f) => isAriaLabelScanned(toPosixRelative(f)));
    expect(scanned.length).toBeGreaterThan(0);
  });

  it("detector 1 (aria-label): finds zero violations across the tree", () => {
    const violations: string[] = [];
    for (const file of allFiles) {
      const relPath = toPosixRelative(file);
      if (!isAriaLabelScanned(relPath)) continue;
      for (const hit of ariaLabelViolations(readFileSync(file, "utf8"))) {
        violations.push(`${relPath}: ${hit}`);
      }
    }
    expect(violations).toEqual([]);
  });

  it("detector 1 (aria-label): rejects an inline known-bad fixture", () => {
    const fixture = `<button aria-label="Close menu">`;
    expect(ariaLabelViolations(fixture)).toHaveLength(1);
  });

  it("detector 2 (JSX text): scans a non-empty set of files", () => {
    const scanned = allFiles.filter((f) => isJsxTextScanned(toPosixRelative(f)));
    expect(scanned.length).toBeGreaterThan(0);
  });

  it("detector 2 (JSX text): finds zero violations across the tree", () => {
    const violations: string[] = [];
    for (const file of allFiles) {
      const relPath = toPosixRelative(file);
      if (!isJsxTextScanned(relPath)) continue;
      for (const hit of jsxTextViolations(readFileSync(file, "utf8"))) {
        violations.push(`${relPath}: ${hit}`);
      }
    }
    expect(violations).toEqual([]);
  });

  it("detector 2 (JSX text): rejects an inline known-bad fixture", () => {
    const fixture = `<span>Sign out</span>`;
    expect(jsxTextViolations(fixture)).toHaveLength(1);
  });
});
