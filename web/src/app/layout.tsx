import type { Metadata, Viewport } from "next";
import { JetBrains_Mono } from "next/font/google";

import "./globals.css";

// Self-hosted at build time: no request to Google from the browser, so the CSP can
// keep font-src 'self'.
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500", "700"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "orqen", template: "%s · orqen" },
  description: "An online judge for AI agents.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#0b0c0d", colorScheme: "dark" };

// Every page carries a per-request CSP nonce, so nothing is prerendered.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={mono.variable}>
      <body>{children}</body>
    </html>
  );
}
