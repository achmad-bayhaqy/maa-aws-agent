import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MAA AWS Agent — Insinyur Cloud Otonom",
  description: "Agen AI otonom untuk operasi cloud AWS: Bedrock AgentCore, MFA TOTP wajib, Live Trace transparan, konfirmasi ganda untuk operasi destruktif.",
  keywords: ["AWS", "Bedrock", "AgentCore", "CloudOps", "AI Agent"],
  icons: {
    icon: "/logo.svg",
    apple: "/logo.svg",
  },
  openGraph: {
    title: "MAA AWS Agent",
    description: "Insinyur cloud otonom di genggaman Anda",
    siteName: "MAA AWS Agent",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
