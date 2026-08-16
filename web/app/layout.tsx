import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI İş Arama Ajanı",
  description:
    "CV'nizi yükleyin, kriterlerinizi belirleyin; ajan ilanları tarayıp size uygunluğuna göre sıralasın.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
