"use client";

import { useMessages, useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
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
 * Presentational current-conditions card. Takes the weather query's `current`
 * block plus its `isPending` / `isError` flags and makes no request of its own,
 * so it owns the same spinner / error / empty ladder as `MapTab`: a pending
 * query shows a spinner, a failed one shows an error — a slow or failed
 * `/weather` never silently renders nothing. The condition string is the
 * localized WMO entry for `weather_code`, falling back to the response's own
 * `description` when the code is not in the map — never an empty condition.
 */
export function TodayWeatherCard({
  current,
  isPending = false,
  isError = false,
}: {
  current: CurrentWeather | undefined;
  isPending?: boolean;
  isError?: boolean;
}) {
  const t = useTranslations("Today.weather");
  const tWmo = useTranslations("Today.weather.wmo");
  const tCommon = useTranslations("Common");
  const tErr = useTranslations("Errors");
  const wmoMap = useWmoMap();

  if (isPending) {
    return (
      <Card className="flex max-w-[28rem] items-center gap-sm text-sm text-muted">
        <Spinner label={t("title")} />
        <span>{tCommon("loading")}</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="max-w-[28rem]">
        <EmptyState
          icon="⚠️"
          title={tErr("somethingWentWrongTitle")}
          hint={tErr("somethingWentWrongHint")}
        />
      </Card>
    );
  }

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
