import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PrivacyShieldAI - Enterprise PII Detection & Redaction SaaS",
  description: "Enterprise-grade multi-tenant PII detection, redaction, risk analytics, and DPDP/GDPR audit compliance platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full">
      <body className={`${inter.className} bg-slate-950 text-slate-100 antialiased h-full overflow-hidden`}>
        {children}
      </body>
    </html>
  );
}
