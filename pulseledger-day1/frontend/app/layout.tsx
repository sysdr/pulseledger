import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PulseLedger",
  description: "180 days to production-grade billing, ledger & agentic fintech infrastructure.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
