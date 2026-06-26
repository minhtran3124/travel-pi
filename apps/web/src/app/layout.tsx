import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

import { AppShell } from "@/components/app-shell/AppShell";
import { ChatWidget } from "@/components/chat/ChatWidget";
import { IdentityProvider } from "@/lib/identity/provider";
import { QueryProvider } from "@/lib/query/provider";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Travel Planner",
  description: "Plan trips, explore places, and manage bookings.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <IdentityProvider>
          <QueryProvider>
            <AppShell>{children}</AppShell>
            <ChatWidget />
          </QueryProvider>
        </IdentityProvider>
      </body>
    </html>
  );
}
