import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulseLedger",
  description: "180 days to production-grade billing, ledger & agentic fintech infrastructure.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="m-0 font-sans antialiased">{children}</body>
    </html>
  );
}
