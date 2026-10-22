"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { Pill, type PillProps } from "@/components/ui/Pill";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";
import { useClimate, useTips, useVisa } from "@/lib/query/guide";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-md rounded-md border border-line bg-panel p-lg shadow-card">
      <h2 className="text-[1.05rem] font-extrabold text-ink">{title}</h2>
      {children}
    </section>
  );
}

/** GET /visa — a failure here must not blank the tips or climate sections. */
function VisaSection({ city }: { city: string }) {
  const t = useTranslations("Guide");
  const { data, isLoading, isError } = useVisa(city);

  return (
    <Section title={t("visa.title")}>
      {isLoading ? (
        <div className="flex justify-center py-lg">
          <Spinner label={t("visa.loadingLabel")} />
        </div>
      ) : isError ? (
        <EmptyState
          icon="⚠️"
          title={t("visa.errorTitle")}
          hint={t("visa.errorHint")}
        />
      ) : !data ? null : !data.found || !data.entry ? (
        <EmptyState
          icon="🛂"
          title={t("visa.notFoundTitle")}
          hint={t("visa.notFoundHint", { country: data.country })}
        />
      ) : (
        <dl className="grid grid-cols-2 gap-sm text-sm">
          <div>
            <dt className="text-muted">{t("visa.visaFreeDays")}</dt>
            <dd className="font-bold text-ink">
              {data.entry.visa_free_days > 0
                ? t("visa.visaFreeDaysValue", {
                    count: data.entry.visa_free_days,
                  })
                : t("visa.visaRequired")}
            </dd>
          </div>
          <div>
            <dt className="text-muted">{t("visa.visaOnArrival")}</dt>
            <dd className="font-bold text-ink">
              {data.entry.visa_on_arrival ? t("visa.yes") : t("visa.no")}
            </dd>
          </div>
          <div>
            <dt className="text-muted">{t("visa.eVisa")}</dt>
            <dd className="font-bold text-ink">
              {data.entry.e_visa ? t("visa.yes") : t("visa.no")}
            </dd>
          </div>
          <div>
            <dt className="text-muted">{t("visa.passportValidity")}</dt>
            <dd className="font-bold text-ink">
              {data.entry.passport_validity_months > 0
                ? t("visa.passportValidityValue", {
                    count: data.entry.passport_validity_months,
                  })
                : t("visa.passportValidityDuration")}
            </dd>
          </div>
          <p className="col-span-2 text-sm text-muted">
            {data.entry.summary}
          </p>
        </dl>
      )}

      {/* Mandatory caveat — the API ships this sentence for a reason, so it
          reaches the traveller unedited whether or not entry data was found. */}
      {data ? (
        <p className="rounded-sm bg-panel-raised px-md py-sm text-xs text-muted">
          {data.disclaimer}
        </p>
      ) : null}
    </Section>
  );
}

/** GET /tips — a failure here must not blank the visa or climate sections. */
function TipsSection({ city }: { city: string }) {
  const t = useTranslations("Guide");
  const { data, isLoading, isError } = useTips(city);

  return (
    <Section title={t("tips.title")}>
      {isLoading ? (
        <div className="flex justify-center py-lg">
          <Spinner label={t("tips.loadingLabel")} />
        </div>
      ) : isError ? (
        <EmptyState
          icon="⚠️"
          title={t("tips.errorTitle")}
          hint={t("tips.errorHint")}
        />
      ) : !data || data.count === 0 ? (
        <EmptyState icon="💡" title={t("tips.emptyTitle")} hint={t("tips.emptyHint")} />
      ) : (
        <ul className="flex flex-col gap-md">
          {data.tips.map((tip) => (
            <li key={tip.id} className="flex flex-col gap-xs">
              <div className="flex items-center gap-sm">
                <Pill
                  variant="topic"
                  tone={tip.category as PillProps["tone"]}
                  label={tip.category}
                />
                <span className="font-bold text-ink">{tip.title}</span>
              </div>
              <p className="text-sm text-muted">{tip.content}</p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** GET /destinations/climate — a failure here must not blank the other two. */
function ClimateSection({ city }: { city: string }) {
  const t = useTranslations("Guide");
  const { data, isLoading, isError } = useClimate(city);

  return (
    <Section title={t("climate.title")}>
      {isLoading ? (
        <div className="flex justify-center py-lg">
          <Spinner label={t("climate.loadingLabel")} />
        </div>
      ) : isError ? (
        <EmptyState
          icon="⚠️"
          title={t("climate.errorTitle")}
          hint={t("climate.errorHint")}
        />
      ) : !data ? null : (
        <div className="flex flex-col gap-md">
          <p className="text-sm text-muted">{data.summary}</p>
          <div className="grid grid-cols-2 gap-sm sm:grid-cols-3">
            {data.months.map((month) => (
              <div
                key={month.month}
                className={cn(
                  "flex flex-col gap-xs rounded-sm bg-panel-raised px-sm py-sm",
                  data.best_months.includes(month.month) && "ring-1 ring-lime",
                )}
              >
                <span className="text-xs font-bold uppercase tracking-[0.04em] text-muted">
                  {month.name}
                </span>
                <span className="text-sm font-bold tabular-nums text-ink">
                  {month.avg_temp_min_c}°–{month.avg_temp_max_c}°C
                </span>
                <span className="text-xs text-muted">{month.comfort}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted">{data.attribution}</p>
        </div>
      )}
    </Section>
  );
}

export default function GuidePage() {
  const t = useTranslations("Guide");
  const params = useParams<{ city: string }>();
  const city = decodeURIComponent(params.city ?? "");

  return (
    <section className="mx-auto flex max-w-[42rem] flex-col gap-lg px-xl py-lg">
      <header className="flex flex-col gap-xs">
        <Link
          href="/places"
          className="inline-flex w-fit items-center gap-xs text-sm font-bold text-muted transition hover:text-ink"
        >
          {t("back")}
        </Link>
        <h1 className="text-2xl font-extrabold text-ink">
          {t("title", { city })}
        </h1>
      </header>

      <VisaSection city={city} />
      <TipsSection city={city} />
      <ClimateSection city={city} />
    </section>
  );
}
