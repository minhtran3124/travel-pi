import { CalendarIcon, PinIcon } from "@/components/trips/tripVisuals";

/**
 * The warm "horizon" pane shown beside the auth forms (login / sign-up).
 *
 * It reuses the product's signature welcome-strip language — a sky→meadow→sunset
 * gradient with a coral flight arc and a paper plane gliding in — so the auth
 * surface feels like the rest of the app, not a bolted-on login. Warmth lives in
 * the gradient, the arc, and the copy (the "well-traveled friend" voice); the
 * one sanctioned lime is the wordmark badge. Hidden below `lg` (the form pane
 * carries a compact wordmark there instead).
 *
 * Motion: the arc draws and the plane lands once on mount, and collapses to the
 * finished state under `prefers-reduced-motion`.
 */
export function AuthHero() {
  return (
    <aside
      className="relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-[clamp(2rem,4vw,3.5rem)]"
      style={{
        background:
          "linear-gradient(150deg, #eaf3ff 0%, #f5fbe3 54%, #ffeede 100%)",
      }}
    >
      {/* Flight sky — coral contrail + landing plane, behind the copy. */}
      <svg
        aria-hidden="true"
        viewBox="0 0 400 600"
        preserveAspectRatio="xMidYMid slice"
        className="pointer-events-none absolute inset-0 size-full"
      >
        {/* soft horizon sun, top-right */}
        <circle cx="350" cy="120" r="150" fill="#ffe9e2" opacity="0.55" />
        {/* origin marker */}
        <circle cx="36" cy="548" r="4" fill="#fb7755" fillOpacity="0.8" />
        {/* the contrail */}
        <path
          className="auth-arc"
          pathLength={1}
          d="M36 548 Q 210 150 372 214"
          fill="none"
          stroke="#fb7755"
          strokeOpacity="0.5"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        {/* waypoint */}
        <circle cx="210" cy="280" r="3" fill="#fb7755" fillOpacity="0.55" />
        {/* the plane, parked at the arc's end */}
        <g
          className="auth-plane"
          transform="translate(372 214) rotate(18)"
          fill="#b4321f"
          fillOpacity="0.9"
        >
          <path d="M14 0 L-10 9 L-3 0 L-10 -9 Z" />
        </g>
      </svg>

      {/* Wordmark */}
      <div className="relative z-10 flex items-center gap-sm text-base font-extrabold tracking-tight text-ink">
        <span className="grid size-7 place-items-center rounded-md bg-lime text-on-accent shadow-sm">
          <PaperPlane />
        </span>
        Travel Planner
      </div>

      {/* Headline + value rows */}
      <div className="relative z-10 flex flex-col gap-lg">
        <div className="flex flex-col gap-sm">
          <h2 className="text-balance text-[clamp(2rem,3vw,2.6rem)] font-extrabold leading-[1.1] tracking-tight text-ink">
            Where to next?
          </h2>
          <p className="max-w-[34ch] text-pretty text-sm leading-relaxed text-ink/70">
            Plan, book, and keep every trip on track — with an agent that does
            the legwork while you stay in control.
          </p>
        </div>

        <ul className="flex flex-col gap-md">
          <ValueRow icon={<PinIcon />} text="Shortlist the places worth your time" />
          <ValueRow icon={<CalendarIcon />} text="Build a day-by-day plan that flexes" />
          <ValueRow icon={<Sparkle />} text="Hand off the busywork to your travel agent" />
        </ul>
      </div>

      {/* Footer note — the friend voice */}
      <p className="relative z-10 text-xs font-medium text-ink/55">
        Built for people with more than one trip on the go.
      </p>

      {/* Scoped, reduced-motion-safe entrance for the arc + plane. */}
      <style>{`
        .auth-arc {
          stroke-dasharray: 1;
          stroke-dashoffset: 1;
          animation: auth-draw 2s cubic-bezier(0.22, 1, 0.36, 1) 0.15s forwards;
        }
        .auth-plane {
          opacity: 0;
          transform-box: fill-box;
          transform-origin: center;
          animation: auth-land 0.5s cubic-bezier(0.22, 1, 0.36, 1) 1.9s forwards;
        }
        @keyframes auth-draw { to { stroke-dashoffset: 0; } }
        @keyframes auth-land {
          from { opacity: 0; }
          to { opacity: 0.9; }
        }
        @media (prefers-reduced-motion: reduce) {
          .auth-arc { animation: none; stroke-dashoffset: 0; }
          .auth-plane { animation: none; opacity: 0.9; }
        }
      `}</style>
    </aside>
  );
}

function ValueRow({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <li className="flex items-center gap-sm text-sm font-medium text-ink/80">
      <span className="grid size-7 shrink-0 place-items-center rounded-md border border-line bg-panel/70 text-coral-ink shadow-sm backdrop-blur-sm">
        {icon}
      </span>
      {text}
    </li>
  );
}

function PaperPlane() {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinejoin="round"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M21 3 3 10.5l6.5 2.5L12 20l9-17Z" />
      <path d="M9.5 13 21 3" />
    </svg>
  );
}

function Sparkle() {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.8 2.8M14.9 14.9l2.8 2.8M17.7 6.3l-2.8 2.8M9.1 14.9l-2.8 2.8" />
    </svg>
  );
}
