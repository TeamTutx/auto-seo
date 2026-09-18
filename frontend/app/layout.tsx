import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { SITE_URL } from "@/lib/site";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
});
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
});
const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

// Google Analytics 4 measurement ID (public by design - it ships in the page).
// Unset in local dev and on any deploy that shouldn't be tracked; the format
// check keeps a typo'd value from being injected into an inline script.
const rawGaId = process.env.NEXT_PUBLIC_GA_ID;
const GA_ID = rawGaId && /^G-[A-Z0-9]+$/.test(rawGaId) ? rawGaId : undefined;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "Signal — SEO audits, rank tracking and AI fixes",
  description:
    "Run on-page SEO audits, track keyword rankings against your competitors, and get AI-written fixes, with real Google Search Console data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${inter.variable} ${jetBrainsMono.variable}`}>
      <body>
        <AuthProvider>{children}</AuthProvider>
        {GA_ID && (
          <>
            <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
            <Script id="ga-init" strategy="afterInteractive">
              {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${GA_ID}');`}
            </Script>
          </>
        )}
      </body>
    </html>
  );
}
