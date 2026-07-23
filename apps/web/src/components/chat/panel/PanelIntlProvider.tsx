"use client";

import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import type { ReactNode } from "react";

import en from "../../../../messages/en.json";
import vi from "../../../../messages/vi.json";

// The side-panel renders its STATIC labels in the language the BACKEND detected
// for the conversation (streamed as `panelLanguage`), which can differ from the
// cookie locale that drives the rest of the app. Both catalogs are imported
// statically and only the `Panel` slice is handed to a nested provider, so the
// payload stays small and this subtree overrides the ambient locale in place.
const CATALOGS: Record<string, AbstractIntlMessages> = { en, vi };

export function PanelIntlProvider({
  language,
  children,
}: {
  language: string;
  children: ReactNode;
}) {
  const catalog = CATALOGS[language] ?? (en as AbstractIntlMessages);
  return (
    <NextIntlClientProvider locale={language} messages={{ Panel: catalog.Panel }}>
      {children}
    </NextIntlClientProvider>
  );
}
