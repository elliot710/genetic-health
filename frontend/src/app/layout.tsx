import type { Metadata } from "next";
import { Geist, Geist_Mono, Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const inter = Inter({subsets:['latin'],variable:'--font-sans'});

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: 'Epigenic — Your Genetic Health Dashboard',
  description: 'Upload your VCF or CSV DNA data and explore 13 personalized health panels: drug responses, disease risk, ancestry, nutrition, sports performance, and more.',
  metadataBase: new URL('https://epigenic.xyz'),
  openGraph: {
    title: 'Epigenic — Genetic Health Insights',
    description: 'Evidence-based genetic analysis across 13 panels. Private, encrypted, and built for curious minds.',
    url: 'https://epigenic.xyz',
    siteName: 'Epigenic',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Epigenic — Genetic Health Insights',
    description: 'Evidence-based genetic analysis across 13 panels.',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={cn("font-sans", inter.variable)}>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var saved=localStorage.getItem('darkMode');if(saved&&JSON.parse(saved))document.documentElement.classList.add('dark');}catch(e){}})();`,
          }}
        />
        {children}
      </body>
    </html>
  );
}
