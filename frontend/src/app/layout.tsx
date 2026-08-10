import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PrivacyShield — privacy operations workspace",
  description: "A privacy operations workspace for PII detection, redaction, risk analytics, and audit readiness.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full">
      <body className="bg-slate-950 text-slate-100 antialiased h-full overflow-hidden">
        {children}
      </body>
    </html>
  );
}
