import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://ricohunt.com"),
  title: "Rico AI — Your AI-Native UAE Career Companion",
  description: "Rico finds jobs that match your profile, scores them by fit, and helps you apply — so you can focus on the right opportunities.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Rico AI — Your AI-Native UAE Career Companion",
    description: "Rico finds jobs that match your profile, scores them by fit, and helps you apply — so you can focus on the right opportunities.",
    type: "website",
    url: "https://ricohunt.com",
    siteName: "Rico AI",
  },
  twitter: {
    card: "summary",
    title: "Rico AI — Your AI-Native UAE Career Companion",
    description: "Rico finds jobs that match your profile, scores them by fit, and helps you apply — so you can focus on the right opportunities.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cabinet+Grotesk:wght@400;500;700;800;900&family=Instrument+Sans:ital,wght@0,400;0,500;1,400&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased bg-[#06060f] text-[#eeeef5] font-[Instrument_Sans,sans-serif]">
        {children}
      </body>
    </html>
  );
}
