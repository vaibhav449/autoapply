import type { Metadata } from "next";
import Link from "next/link";
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
  title: "AutoApply",
  description: "Personalized job discovery and application automation.",
};

const NAV_LINKS = [
  { href: "/profiles", label: "Profiles" },
  { href: "/applications", label: "Applications" },
  { href: "/review", label: "Review" },
  { href: "/pending", label: "Pending" },
  { href: "/analytics", label: "Analytics" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <header className="site-header">
          <div className="site-header-inner">
            <Link href="/" className="site-title">
              AutoApply
            </Link>
            <ul className="site-nav">
              {NAV_LINKS.map((link) => (
                <li key={link.href}>
                  <Link href={link.href}>{link.label}</Link>
                </li>
              ))}
            </ul>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
