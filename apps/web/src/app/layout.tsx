import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "MyTrackIn", template: "%s · MyTrackIn" },
  description: "Vendor-chain payments, timesheets, contracts and compliance for staffing companies.",
  robots: { index: false, follow: false },
  icons: { icon: "/favicon.png", apple: "/logo-mark.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [{ media: "(prefers-color-scheme: dark)", color: "#081826" }, { color: "#f5f9fc" }],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
