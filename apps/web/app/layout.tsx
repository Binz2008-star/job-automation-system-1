import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://ricohunt.com"),
  title: "Rico AI — Autonomous AI Job Search",
  description: "Rico finds jobs that match your profile, scores them by fit, and helps you apply — so you can focus on the right opportunities.",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "Rico AI — Autonomous AI Job Search",
    description: "Rico finds jobs that match your profile, scores them by fit, and helps you apply — so you can focus on the right opportunities.",
    type: "website",
    url: "https://ricohunt.com",
    siteName: "Rico AI",
  },
  twitter: {
    card: "summary",
    title: "Rico AI — Autonomous AI Job Search",
    description: "Rico finds jobs that match your profile, scores them by fit, and helps you apply — so you can focus on the right opportunities.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-zinc-950 text-zinc-100">{children}</body>
    </html>
  );
}
