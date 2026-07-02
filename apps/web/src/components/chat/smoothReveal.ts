/**
 * Smooth reveal (typewriter drip) for streamed assistant text.
 *
 * Wire tokens arrive in fast, uneven bursts; appending each straight to state
 * makes the text jump. This controller buffers incoming text and drains it into
 * `append` at a bounded character rate via requestAnimationFrame, so the reveal
 * reads slower and smoother. The rate scales up with backlog so it never lags
 * more than ~`maxLagSec` behind the wire, and it keeps draining after the stream
 * ends until the buffer empties.
 *
 * Plain (non-React) so the recursive rAF loop and mutable state live outside the
 * hook-rules linter; the hook instantiates one per conversation.
 */
export interface SmoothReveal {
  /** Buffer more text for `id` and (re)start the drip loop. */
  enqueue(id: string, text: string): void;
  /** Drop buffered text and blank the message (agent revised its answer). */
  reset(id: string): void;
  /** Render any remaining buffer immediately (a new turn is starting). */
  flush(): void;
  /** Drop buffered text without rendering it (new conversation). */
  clear(): void;
  /** Cancel the loop and drop state (component unmount). */
  dispose(): void;
}

export interface SmoothRevealOptions {
  /** Base reveal speed in characters/second. Lower = slower. */
  charsPerSec?: number;
  /** Max seconds the reveal may lag behind the wire before it speeds up. */
  maxLagSec?: number;
}

export function createSmoothReveal(
  append: (id: string, text: string) => void,
  blank: (id: string) => void,
  options: SmoothRevealOptions = {},
): SmoothReveal {
  const charsPerSec = options.charsPerSec ?? 90;
  const maxLagSec = options.maxLagSec ?? 0.6;

  let buffer = "";
  let targetId: string | null = null;
  let raf: number | null = null;
  let lastTs = 0;

  const drain = (ts: number) => {
    const pending = buffer.length;
    if (targetId === null || pending === 0) {
      raf = null;
      return;
    }
    const dt = ts - (lastTs || ts);
    lastTs = ts;
    // Speed up when backlogged so the reveal never falls too far behind.
    const perSec = Math.max(charsPerSec, pending / maxLagSec);
    const count = Math.min(pending, Math.max(1, Math.round((dt / 1000) * perSec)));
    const slice = buffer.slice(0, count);
    buffer = buffer.slice(count);
    append(targetId, slice);
    raf = requestAnimationFrame(drain);
  };

  const ensureLoop = () => {
    if (raf === null) {
      lastTs = 0;
      raf = requestAnimationFrame(drain);
    }
  };

  const cancelLoop = () => {
    if (raf !== null) {
      cancelAnimationFrame(raf);
      raf = null;
    }
  };

  return {
    enqueue(id, text) {
      targetId = id;
      buffer += text;
      ensureLoop();
    },
    reset(id) {
      cancelLoop();
      buffer = "";
      blank(id);
    },
    flush() {
      cancelLoop();
      const rest = buffer;
      buffer = "";
      if (rest && targetId !== null) append(targetId, rest);
    },
    clear() {
      cancelLoop();
      buffer = "";
    },
    dispose() {
      cancelLoop();
      buffer = "";
    },
  };
}
