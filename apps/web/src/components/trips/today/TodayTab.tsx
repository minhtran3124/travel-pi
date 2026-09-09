"use client";

import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { TodayAirQualityCard } from "@/components/trips/today/TodayAirQualityCard";
import { TodayDirections } from "@/components/trips/today/TodayDirections";
import { TodayWeatherCard } from "@/components/trips/today/TodayWeatherCard";
import {
  isWithinTrip,
  nextUnstarted,
  todayIso,
} from "@/components/trips/today/todaySelectors";
import { useAirQuality, useDayPlan, useWeather } from "@/lib/query/today";
import { useTrip } from "@/lib/query/trips";

/**
 * The Today tab. Reads the trip, computes the browser-local calendar date, and
 * branches on the trip window: outside it, the dated "not in progress" state
 * (or the no-dates variant); inside it, today's ordered plan, then weather and
 * air quality for `trip.city` (or the no-destination state when `city` is null),
 * then directions to the next unstarted item.
 *
 * Reading the clock is fine here — this tab is the composition seam; the pure
 * date rules it composes (`todaySelectors`) take their "now" as an argument and
 * are swept across anchors in their own test.
 */
export function TodayTab({ tripId }: { tripId: string }) {
  const t = useTranslations("Today");
  const { data: trip, isPending, isError } = useTrip(tripId);

  const today = todayIso(new Date());
  const within = trip
    ? isWithinTrip(today, trip.start_date, trip.end_date)
    : false;
  const city = trip?.city ?? "";

  // Hooks run unconditionally; the "" input disables the query when the tab is
  // outside the trip window or the trip has no city, so no request is made.
  const dayPlan = useDayPlan(tripId, within ? today : "");
  const weather = useWeather(within ? city : "");
  const airQuality = useAirQuality(within ? city : "");

  const items = dayPlan.data?.items ?? [];
  const route = nextUnstarted(items);

  return (
    <section className="flex flex-col gap-md">
      <h2 className="text-lg font-extrabold text-ink">{t("tab")}</h2>

      {isPending ? (
        <Card className="flex items-center gap-sm text-sm text-muted">
          <Spinner label={t("tab")} />
        </Card>
      ) : isError || !trip ? (
        <Card>
          <EmptyState icon="📅" title={t("notInProgress.title")} />
        </Card>
      ) : !within ? (
        <Card>
          <EmptyState
            icon="📅"
            title={t("notInProgress.title")}
            hint={
              trip.start_date
                ? t("notInProgress.dates", {
                    start: trip.start_date,
                    end: trip.end_date ?? trip.start_date,
                  })
                : t("notInProgress.noDates")
            }
          />
        </Card>
      ) : (
        <>
          <Card className="flex flex-col gap-sm">
            <h3 className="text-lg font-extrabold text-ink">
              {t("plan.title")}
            </h3>
            {dayPlan.isPending ? (
              <div className="flex items-center gap-sm text-sm text-muted">
                <Spinner label={t("plan.title")} />
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                icon="🗓️"
                title={t("plan.emptyTitle")}
                hint={t("plan.emptyHint")}
              />
            ) : (
              <ul className="flex flex-col gap-sm">
                {items.map((entry) => (
                  <li
                    key={entry.item.id}
                    className="flex flex-col gap-xs border-b border-line pb-sm last:border-b-0 last:pb-0"
                  >
                    <span className="text-sm font-semibold text-ink">
                      {entry.item.title}
                    </span>
                    {entry.travel_to_next_minutes != null ? (
                      <span className="text-xs text-muted">
                        {t("plan.travelToNext", {
                          minutes: entry.travel_to_next_minutes,
                        })}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {city ? (
            <>
              <TodayWeatherCard current={weather.data?.current} />
              <TodayAirQualityCard data={airQuality.data} />
            </>
          ) : (
            <Card>
              <EmptyState
                icon="📍"
                title={t("noDestination.title")}
                hint={t("noDestination.hint")}
              />
            </Card>
          )}

          <TodayDirections
            previous={route?.previous ?? null}
            next={route?.next ?? null}
          />
        </>
      )}
    </section>
  );
}
