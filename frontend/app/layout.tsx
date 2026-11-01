import React from "react";
import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "../components/Navbar";
import { Container } from "../components/Container";
import { translate } from "../lib/i18n";

export const metadata: Metadata = {
  title: `${translate("brand.name")} — ${translate("brand.tagline")}`,
  description: translate("hero.description"),
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-indigo-600 focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white focus:shadow-lg"
        >
          {translate("a11y.skipToContent")}
        </a>

        <Navbar />

        <main id="main-content" className="py-10 sm:py-14">
          {children}
        </main>

        <footer className="border-t border-slate-200 bg-white py-8 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
          <Container className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p>{translate("footer.summary")}</p>
            <p>{translate("footer.privacyNote")}</p>
          </Container>
        </footer>
      </body>
    </html>
  );
}
