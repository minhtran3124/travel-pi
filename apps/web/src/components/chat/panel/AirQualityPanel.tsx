"use client";

import { useTranslations } from "next-intl";

import type {
  AirQualityPanelData,
  AirQualityPanelDay,
  AirQualityPanelPollutant,
  AqiBand,
} from "@/lib/stream/panel";

/**
 * Air-quality side-panel — a React projection of the dashboard's
 * `air_quality.html` view (specs/agent-side-panel). A band-tinted hero shows the
 * current US-AQI dial, category badge + health advice, and a 0–300+ scale
 * marker; a pollutant grid (PM2.5/PM10/O₃/NO₂/SO₂/CO) and a peak-AQI forecast
 * row follow. Pure render — emoji/advice/band come pre-computed from the BE.
 */

/** US-AQI band → two dark gradient stops + an RGB glow triple (EPA colour ramp). */
const BAND: Record<AqiBand, { cg1: string; cg2: string; glow: string }> = {
  good: { cg1: "#0e3a2a", cg2: "#123330", glow: "52, 211, 153" },
  moderate: { cg1: "#3a3410", cg2: "#332b12", glow: "250, 204, 21" },
  usg: { cg1: "#3d2710", cg2: "#33220f", glow: "251, 146, 60" },
  unhealthy: { cg1: "#3d1414", cg2: "#2f1212", glow: "248, 113, 113" },
  vunhealthy: { cg1: "#2c143c", cg2: "#221830", glow: "192, 132, 252" },
  hazardous: { cg1: "#3a0e1e", cg2: "#2a0c18", glow: "244, 114, 182" },
  unknown: { cg1: "#232c35", cg2: "#20272c", glow: "148, 163, 184" },
};

const SCALE_TRACK =
  "linear-gradient(90deg, #34d399 0%, #facc15 17%, #fb923c 33%, #f87171 50%, #c084fc 67%, #f472b6 100%)";

function glowOf(band: AqiBand): string {
  return (BAND[band] ?? BAND.unknown).glow;
}

function heroBackground(band: AqiBand): string {
  const b = BAND[band] ?? BAND.unknown;
  return [
    `radial-gradient(130% 150% at 100% 0%, rgba(${b.glow}, .26), transparent 58%)`,
    `linear-gradient(135deg, ${b.cg1}, ${b.cg2})`,
  ].join(", ");
}

function Pollutant({ p }: { p: AirQualityPanelPollutant }) {
  return (
    <div className="rounded-[12px] border border-line bg-panel-raised px-3.5 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-extrabold text-ink">{p.label}</span>
        <span className="truncate text-[0.66rem] font-semibold text-muted">
          {p.desc}
        </span>
      </div>
      <div className="mt-1.5 text-xl font-extrabold tabular-nums text-ink">
        {p.value != null ? (
          <>
            {p.value.toFixed(1)}
            <span className="ml-1 text-xs font-semibold text-muted">{p.unit}</span>
          </>
        ) : (
          <span className="text-muted">—</span>
        )}
      </div>
    </div>
  );
}

function ForecastCard({ day, isToday }: { day: AirQualityPanelDay; isToday: boolean }) {
  const t = useTranslations("Panel");
  const glow = glowOf(day.band);
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
            {t("airQuality.today")}
          </span>
        ) : (
          day.date
        )}
      </div>
      <div className="relative z-[1] text-2xl leading-none">{day.emoji}</div>
      <div
        className="text-2xl font-extrabold leading-none tabular-nums"
        style={{ color: `rgb(${glow})` }}
      >
        {day.max_us_aqi ?? "—"}
      </div>
      <div className="min-h-[2.2em] text-[0.68rem] font-semibold text-muted">
        {day.category}
      </div>
    </div>
  );
}

export function AirQualityPanel({ data }: { data: AirQualityPanelData }) {
  const t = useTranslations("Panel");
  const {
    location_name,
    country,
    timezone,
    time,
    us_aqi,
    category,
    emoji,
    band,
    advice,
    pollutants,
    forecast,
    attribution,
  } = data;
  const place = country ? `${location_name}, ${country}` : location_name;
  const glow = glowOf(band);
  const markerPct =
    us_aqi != null ? Math.min(100, Math.max(0, (us_aqi / 300) * 100)) : null;

  return (
    <div className="h-full overflow-y-auto p-md">
      <div
        className="relative overflow-hidden rounded-[16px] border border-line p-lg text-white"
        style={{ background: heroBackground(band) }}
      >
        <div className="relative z-[1] flex flex-wrap items-center gap-md">
          <div
            className="flex h-[110px] w-[110px] shrink-0 flex-col items-center justify-center rounded-full"
            style={{
              background: `radial-gradient(circle at 50% 40%, rgba(${glow}, .18), transparent 70%)`,
              boxShadow: `inset 0 0 0 4px rgba(${glow}, .55), inset 0 0 0 9px rgba(${glow}, .12)`,
            }}
          >
            <div
              className="text-4xl font-extrabold leading-none tracking-tight tabular-nums"
              style={{ color: `rgb(${glow})` }}
            >
              {us_aqi ?? "—"}
            </div>
            <div className="mt-1 text-[0.6rem] font-bold uppercase tracking-widest text-white/70">
              {t("airQuality.usAqi")}
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-1.5">
            <span
              className="inline-flex w-fit items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-extrabold"
              style={{ background: `rgba(${glow}, .16)`, borderColor: `rgba(${glow}, .5)` }}
            >
              {emoji} {category}
            </span>
            <div className="text-sm font-semibold text-white/85">{advice}</div>
            <div className="truncate text-xs text-white/60 tabular-nums">
              📍 {place} · 🕑 {time.replace("T", " ")} · 🌐 {timezone}
            </div>
          </div>
        </div>

        {markerPct != null && (
          <div className="relative z-[1] mt-5">
            <div className="h-2 rounded-full" style={{ background: SCALE_TRACK }} />
            <div
              className="absolute -top-[3px] -translate-x-1/2"
              style={{ left: `${markerPct}%` }}
            >
              <span className="block h-3.5 w-3.5 rounded-full bg-white shadow-[0_0_0_3px_rgba(0,0,0,.35),0_0_8px_rgba(255,255,255,.6)]" />
            </div>
            <div className="mt-1.5 flex justify-between text-[0.66rem] font-bold text-white/60">
              <span>{t("airQuality.scaleLow")}</span>
              <span>{t("airQuality.scaleHigh")}</span>
            </div>
          </div>
        )}
      </div>

      <div className="mt-3.5 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        {pollutants.map((p) => (
          <Pollutant key={p.label} p={p} />
        ))}
      </div>

      {forecast.length > 0 && (
        <>
          <h2 className="mb-2.5 mt-5 text-xs font-extrabold uppercase tracking-wide text-muted">
            {t("airQuality.forecastHeading")}
          </h2>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-2.5">
            {forecast.map((day, i) => (
              <ForecastCard key={day.date} day={day} isToday={i === 0} />
            ))}
          </div>
        </>
      )}

      <div className="mt-3.5 text-right text-[0.71rem] text-muted">{attribution}</div>
    </div>
  );
}
