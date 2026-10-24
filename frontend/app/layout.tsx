import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FrameFlow — Drama & Entertainment Shorts Cutter",
  description: "Turn long-form drama into 60-second vertical clips with a consistent watermark. Upload, process and download your shorts in one ZIP.",
  applicationName: "FrameFlow Shorts Cutter",
  themeColor: "#0b0b12"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
