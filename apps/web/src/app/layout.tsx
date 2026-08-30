import type { Metadata } from "next";

import "maplibre-gl/dist/maplibre-gl.css";
import "@watergis/maplibre-gl-terradraw/dist/maplibre-gl-terradraw.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "CropSage",
  description: "Preliminary crop suitability planning for Texas farms.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
