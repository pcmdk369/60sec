import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Drama & Entertainment Shorts Cutter",
  description: "Cut videos into 60-second vertical clips."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
