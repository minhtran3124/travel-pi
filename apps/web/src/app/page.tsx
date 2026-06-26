// Wiring proof for the monorepo: this server component fetches a real endpoint
// from the FastAPI backend (apps/api) at request time and renders the result.
// Run both with `make api` (BE on :8000) and `make web` (FE on :3000).

export const dynamic = "force-dynamic";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CITY = "Da Nang";

type WeatherResult =
  | { ok: true; data: unknown }
  | { ok: false; error: string };

async function getWeather(): Promise<WeatherResult> {
  try {
    const res = await fetch(
      `${API_URL}/weather?city=${encodeURIComponent(CITY)}&days=3`,
      { cache: "no-store" },
    );
    if (!res.ok) {
      return { ok: false, error: `Backend responded ${res.status}` };
    }
    return { ok: true, data: await res.json() };
  } catch (e) {
    return {
      ok: false,
      error: `Could not reach the backend at ${API_URL} — is \`make api\` running? (${
        e instanceof Error ? e.message : String(e)
      })`,
    };
  }
}

export default async function Home() {
  const result = await getWeather();

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-16 font-sans">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Travel Planner — monorepo</h1>
        <p className="text-sm text-zinc-500">
          Next.js frontend (<code>apps/web</code>) talking to the FastAPI backend (
          <code>apps/api</code>).
        </p>
      </header>

      <section className="rounded-lg border border-zinc-200 p-5 dark:border-zinc-800">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500">
          GET /weather?city={CITY}
        </h2>
        {result.ok ? (
          <pre className="overflow-x-auto rounded-md bg-zinc-50 p-4 text-xs leading-relaxed dark:bg-zinc-900">
            {JSON.stringify(result.data, null, 2)}
          </pre>
        ) : (
          <p className="rounded-md bg-amber-50 p-4 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
            {result.error}
          </p>
        )}
      </section>
    </main>
  );
}
