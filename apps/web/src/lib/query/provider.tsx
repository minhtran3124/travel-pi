"use client";

import {
  isServer,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

/**
 * Returns a QueryClient: a fresh one per request on the server, a module-level
 * singleton in the browser (so it survives re-renders / suspense).
 */
export function getQueryClient(): QueryClient {
  if (isServer) {
    return makeQueryClient();
  }
  if (browserQueryClient === undefined) {
    browserQueryClient = makeQueryClient();
  }
  return browserQueryClient;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(getQueryClient);

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
