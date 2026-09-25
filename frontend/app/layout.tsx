import "./globals.css";
import type { ReactNode } from "react";
import { Nav } from "@/components/ui/Nav";
import { AssistantDock } from "@/components/ui/AssistantDock";
import { DemoBanner } from "@/components/ui/DemoBanner";

export const metadata = {
  title: "HTPP Digital Shadow",
  description: "Digital shadow of industrial batch reactors (demo / Excel seed)",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Sora:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <header className="app-chrome">
          <DemoBanner />
          <Nav />
        </header>
        {children}
        <AssistantDock />
      </body>
    </html>
  );
}
