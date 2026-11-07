import type { Metadata } from "next";
import { Bricolage_Grotesque, Hanken_Grotesk } from "next/font/google";
import "./globals.css";

const displayFont = Bricolage_Grotesque({ variable: "--font-display", subsets: ["latin"] });
const bodyFont = Hanken_Grotesk({ variable: "--font-body", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Nuse — your career desk",
  description: "Capture useful things, track your applications, and keep moving.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return <html lang="en" className={`${displayFont.variable} ${bodyFont.variable}`}><body>{children}</body></html>;
}
