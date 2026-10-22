"use client";

import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import type { AirQualityResponse } from "@/lib/query/today";

export type AqiBand =
  | "good"
  | "moderate"
  | "unhealthySensitive"
  | "unhealthy"
  | "veryUnhealthy"
  | "hazardous";

/**
 * Map a US AQI integer to its published band. Breakpoints are the EPA's:
 * 0–50 good, 51–100 moderate, 101–150 unhealthy for sensitive groups,
 * 151–200 unhealthy, 201–300 very unhealthy, 301+ hazardous. The band key
 * matches `Today.air.band.<band>` in the message catalogs.
 */
export function aqiBand(usAqi: number): AqiBand {
  if (usAqi <= 50) return "good";
  if (usAqi <= 100) return "moderate";
  if (usAqi <= 150) return "unhealthySensitive";
  if (usAqi <= 200) return "unhealthy";
  if (usAqi <= 300) return "veryUnhealthy";
  return "hazardous";
}

/**
 * Presentational air-quality card. Takes the air-quality query's `data` plus its
 * `isPending` / `isError` flags and makes no request of its own, so it owns the
 * same spinner / error / empty ladder as the weather card: a pending query shows
 * a spinner, a failed one shows an error — a slow or failed `/air-quality` never
 * silently renders nothing. Renders a localized band derived from the `us_aqi`
 * integer; when `us_aqi` is null it falls back to the API's own `category` string
 * and omits the numeric reading. PM2.5 shows only when the response carries it.
 */
export function TodayAirQualityCard({
  data,
  isPending = false,
  isError = false,
}: {
  data: AirQualityResponse | undefined;
  isPending?: boolean;
  isError?: boolean;
}) {
  const t = useTranslations("Today.air");
  const tCommon = useTranslations("Common");
  const tErr = useTranslations("Errors");

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

  if (!data) return null;

  const { us_aqi, category, pm2_5 } = data;

  return (
    <Card className="flex max-w-[28rem] flex-col gap-sm">
      <h3 className="text-lg font-extrabold text-ink">{t("title")}</h3>
      {us_aqi != null ? (
        <div className="flex items-baseline gap-sm">
          <span className="text-2xl font-extrabold text-ink">{us_aqi}</span>
          <span className="text-sm text-muted">{t("aqi")}</span>
          <span className="text-sm font-semibold text-ink">
            {t(`band.${aqiBand(us_aqi)}`)}
          </span>
        </div>
      ) : (
        <p className="text-sm font-semibold text-ink">{category}</p>
      )}
      {pm2_5 != null ? (
        <p className="text-sm text-muted">
          {t("pm25")}: <span className="text-ink">{pm2_5}</span>
        </p>
      ) : null}
    </Card>
  );
}
