"use client";

import { useTranslations } from "next-intl";

import type {
  WeatherCondition,
  WeatherPanelData,
  WeatherPanelDay,
} from "@/lib/stream/panel";

/**
 * Weather side-panel — a React projection of the dashboard's `weather.html`
 * forecast view (specs/agent-side-panel). A condition-tinted hero shows current
 * conditions (emoji, temperature, feels-like, humidity, wind, updated time,
 * timezone); a responsive grid of forecast cards follows, each with a TODAY tag
 * on the first day, high/low temps colored by a perceptual ramp, and a
 * precipitation-probability bar. Pure render — no network, no map bundle.
 */

/** Sky-mood → two dark gradient stops + an RGB glow triple (mirror of cond palette). */
const CONDITION: Record<
  WeatherCondition,
  { cg1: string; cg2: string; glow: string }
> = {
  clear: { cg1: "#0e3a48", cg2: "#123330", glow: "251, 191, 36" },
  partly: { cg1: "#0f3344", cg2: "#143531", glow: "125, 211, 252" },
  cloud: { cg1: "#232c35", cg2: "#20272c", glow: "148, 163, 184" },
  rain: { cg1: "#0c2b44", cg2: "#102230", glow: "56, 189, 248" },
  snow: { cg1: "#163139", cg2: "#1b2e33", glow: "165, 243, 252" },
  storm: { cg1: "#221a3c", cg2: "#181830", glow: "167, 139, 250" },
};

/** Perceptual cold→hot text-color ramp for temperatures (°C). */
function tempColor(t: number): string {
  if (t <= 0) return "#93c5fd";
  if (t < 10) return "#7dd3fc";
  if (t < 18) return "#5eead4";
  if (t < 25) return "#86efac";
  if (t < 31) return "#fcd34d";
  return "#fb923c";
}

function heroBackground(condition: WeatherCondition): string {
  const c = CONDITION[condition] ?? CONDITION.rain;
  return [
    `radial-gradient(130% 150% at 100% 0%, rgba(${c.glow}, .26), transparent 58%)`,
    `linear-gradient(135deg, ${c.cg1}, ${c.cg2})`,
  ].join(", ");
}

function ForecastCard({ day, isToday }: { day: WeatherPanelDay; isToday: boolean }) {
  const t = useTranslations("Panel");
  const glow = (CONDITION[day.condition] ?? CONDITION.rain).glow;
  return (
    <div
      className="relative flex flex-col items-center gap-1.5 overflow-hidden rounded-[12px] border border-line bg-panel-raised px-2.5 py-3 text-center"
      style={
        isToday
          ? { borderColor: `rgba(${glow}, .55)`, boxShadow: `0 0 0 1px rgba(${glow}, .25)` }
          : undefined
      }
    >
      <span
        className="pointer-events-none absolute inset-x-0 top-0 h-[72px]"
        style={{
          background: `radial-gradient(120% 90% at 50% 0%, rgba(${glow}, .18), transparent 72%)`,
        }}
      />
      <div className="relative z-[1] min-h-[1.2em] text-xs font-bold tabular-nums text-muted">
        {isToday ? (
          <span
            className="inline-block rounded-full px-2 py-px text-[0.66rem] font-extrabold uppercase tracking-wide text-ink"
            style={{ background: `rgba(${glow}, .18)` }}
          >
            {t("weather.today")}
          </span>
        ) : (
          day.date
        )}
      </div>
      <div className="relative z-[1] text-[2rem] leading-none">{day.emoji}</div>
      <div className="min-h-[2.4em] text-xs font-semibold text-muted">
        {day.description}
      </div>
      <div className="tabular-nums">
        <span
          className="text-lg font-extrabold"
          style={{ color: tempColor(day.temp_max_c) }}
        >
          {Math.round(day.temp_max_c)}°
        </span>
        <span className="ml-1.5 text-base font-bold text-muted">
          {Math.round(day.temp_min_c)}°
        </span>
      </div>
      {day.precipitation_probability_max != null && (
        <div className="mt-px flex w-full flex-col items-center gap-1">
          <span className="text-xs font-bold text-sky-500">
            💧 {day.precipitation_probability_max}%
          </span>
          <span className="h-[5px] w-[78%] overflow-hidden rounded-full bg-sky-500/15">
            <i
              className="block h-full rounded-full bg-sky-500"
              style={{ width: `${day.precipitation_probability_max}%` }}
            />
          </span>
        </div>
      )}
    </div>
  );
}

export function WeatherPanel({ data }: { data: WeatherPanelData }) {
  const t = useTranslations("Panel");
  const { current, daily, location_name, country, timezone, attribution } = data;
  const place = country ? `${location_name}, ${country}` : location_name;

  return (
    <div className="h-full overflow-y-auto p-md">
      <div
        className="relative overflow-hidden rounded-[16px] border border-line p-lg text-white"
        style={{ background: heroBackground(current.condition) }}
      >
        <div className="relative z-[1] flex items-center gap-md">
          <div className="text-6xl leading-none">{current.emoji}</div>
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="text-5xl font-extrabold leading-none tracking-tight tabular-nums">
              {Math.round(current.temperature_c)}
              <span className="ml-0.5 text-2xl font-bold opacity-70">°C</span>
            </div>
            <div className="text-base font-bold">{current.description}</div>
            <div className="text-sm text-white/70">
              {t("weather.feelsLike", { temp: Math.round(current.apparent_temperature_c) })}
            </div>
            <div className="truncate text-xs text-white/60">📍 {place}</div>
          </div>
        </div>

        <div className="relative z-[1] mt-md grid grid-cols-2 gap-x-6 gap-y-3 border-t border-white/15 pt-md">
          <Stat label={`💧 ${t("weather.humidity")}`} value={`${current.relative_humidity}%`} />
          <Stat
            label={`💨 ${t("weather.wind")}`}
            value={
              <>
                {Math.round(current.wind_speed_kmh)}{" "}
                <small className="text-xs font-semibold text-white/70">
                  {t("weather.windUnit")}
                </small>
              </>
            }
          />
          <Stat label={`🕑 ${t("weather.updated")}`} value={current.time.replace("T", " ")} />
          <Stat label={`🌐 ${t("weather.timezone")}`} value={timezone} />
        </div>
      </div>

      <div className="mt-3.5 grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-2.5">
        {daily.map((day, i) => (
          <ForecastCard key={day.date} day={day} isToday={i === 0} />
        ))}
      </div>

      <div className="mt-3.5 text-right text-[0.71rem] text-muted">{attribution}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="truncate text-[0.64rem] font-bold uppercase tracking-wide text-white/70">
        {label}
      </span>
      <b className="truncate text-sm font-bold tabular-nums">{value}</b>
    </div>
  );
}
