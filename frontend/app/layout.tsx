import "./globals.css";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "껄스닥",
  description:
    "내 주식, 그리고 그때 살걸 그 종목까지. 후회가 상장되는 거래소, 껄스닥. 전일 종가 기준 · 투자 자문 아님.",
  openGraph: {
    title: "껄스닥",
    description: "그때 살걸 그 종목, 지금 얼마였을까. 후회가 상장되는 거래소.",
    locale: "ko_KR",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "껄스닥",
    description: "그때 살걸 그 종목, 지금 얼마였을까. 후회가 상장되는 거래소.",
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#000",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
