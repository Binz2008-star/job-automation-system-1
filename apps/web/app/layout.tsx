import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://ricohunt.com"),
  title: "Rico AI — Your Autonomous UAE Career Agent",
  description: "Stop searching for UAE jobs manually. Rico AI finds matching jobs, scores them, sends Telegram alerts, helps you apply, and tracks everything — so you never have to scroll job boards again.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Rico AI — Your Autonomous UAE Career Agent",
    description: "The AI career agent that job-hunts for you in the UAE. Rico finds, scores, alerts, and tracks — and never applies without your approval.",
    type: "website",
    url: "https://ricohunt.com",
    siteName: "Rico AI",
  },
  twitter: {
    card: "summary",
    title: "Rico AI — Your Autonomous UAE Career Agent",
    description: "The AI career agent that job-hunts for you in the UAE. Rico finds, scores, alerts, and tracks — and never applies without your approval.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cabinet+Grotesk:wght@400;500;700;800;900&family=Instrument+Sans:ital,wght@0,400;0,500;1,400&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased bg-[#06060f] text-[#eeeef5] font-[Instrument_Sans,sans-serif]">
        {children}
      </body>
    </html>
  );
}
