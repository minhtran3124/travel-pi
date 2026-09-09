"use client";

import { useMessages, useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import type { WeatherResponse } from "@/lib/query/today";

type CurrentWeather = WeatherResponse["current"];

/**
 * The localized WMO map, read raw so an unknown `weather_code` can fall back to
 * the API's own `description` without `t.has` (forbidden by the slice's i18n rule).
 */
function useWmoMap(): Record<string, string> {
  const messages = useMessages() as {
    Today?: { weather?: { wmo?: Record<string, string> } };
  };
  return messages.Today?.weather?.wmo ?? {};
}

/**
 * Presentational current-conditions card. Takes the weather response's `current`
 * block (or nothing) and makes no request of its own. The condition string is the
 * localized WMO entry for `weather_code`, falling back to the response's own
 * `description` when the code is not in the map — never an empty condition.
 */
export function TodayWeatherCard({
  current,
}: {
  current: CurrentWeather | undefined;
}) {
  const t = useTranslations("Today.weather");
  const tWmo = useTranslations("Today.weather.wmo");
  const wmoMap = useWmoMap();

  if (!current) return null;

  const codeKey = String(current.weather_code);
  const condition = codeKey in wmoMap ? tWmo(codeKey) : current.description;

  const rows: Array<{ label: string; value: string }> = [
    { label: t("temperature"), value: `${Math.round(current.temperature_c)}°C` },
    {
      label: t("feelsLike"),
      value: `${Math.round(current.apparent_temperature_c)}°C`,
    },
    { label: t("humidity"), value: `${Math.round(current.relative_humidity)}%` },
    { label: t("wind"), value: `${Math.round(current.wind_speed_kmh)} km/h` },
  ];

  return (
    <Card className="flex max-w-[28rem] flex-col gap-sm">
      <div className="flex items-baseline justify-between gap-sm">
        <h3 className="text-lg font-extrabold text-ink">{t("title")}</h3>
        <span className="text-sm font-semibold text-muted">{condition}</span>
      </div>
      <dl className="grid grid-cols-2 gap-sm">
        {rows.map((row) => (
          <div key={row.label} className="flex flex-col">
            <dt className="text-xs text-muted">{row.label}</dt>
            <dd className="text-sm font-semibold text-ink">{row.value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
