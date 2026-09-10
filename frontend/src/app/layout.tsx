import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BISKATE ANALYTICS — NFL Player Prop Value Engine",
  description: "Plataforma quantitativa de apostas de valor (+EV), machine learning e projeções avançadas para Player Props da NFL.",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/images/biskate-analytics-monogram-champagne-gold.svg", type: "image/svg+xml" },
    ],
    apple: "/images/biskate-analytics-monogram-champagne-gold.svg",
    shortcut: "/favicon.ico",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
