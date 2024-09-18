import type { Metadata } from "next";
import { DM_Sans } from "next/font/google"; // Import DM Sans
import "./globals.css";
import { SiteHeader } from "@/components/site-header";

// Configure DM Sans with specified options
const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "700"], // Specify the weights you need
  style: ["normal", "italic"], // Specify styles if needed
});

export const metadata: Metadata = {
  title: "Sigma Computing Embed-SDK",
  description: "Sigma Computing Embed SDK",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={dmSans.className}> {/* Apply DM Sans font class */}
        <div className="relative flex flex-col h-screen">
          <SiteHeader />
          <div className="flex-1">
            <main className="container mx-auto p-8">
              <div className="grid grid-cols-1 gap-8">
                {children}
              </div>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}