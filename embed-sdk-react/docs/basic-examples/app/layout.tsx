import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { SiteHeader } from "@/components/site-header";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Sigma Computing Embed Docs",
  description: "Documentation site for Sigma Computing Embed SDK",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="relative flex flex-col h-screen">
          <SiteHeader />
          <div className="flex-1">{children}</div>
        </div>
      </body>
    </html>
  );
}
