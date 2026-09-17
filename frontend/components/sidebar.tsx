"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChartIcon,
  BriefcaseIcon,
  ClipboardCheckIcon,
  ClockIcon,
  UsersIcon,
} from "@/components/icons";
import type { ComponentType, SVGProps } from "react";

const NAV_LINKS: { href: string; label: string; icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { href: "/profiles", label: "Profiles", icon: UsersIcon },
  { href: "/applications", label: "Applications", icon: BriefcaseIcon },
  { href: "/review", label: "Review", icon: ClipboardCheckIcon },
  { href: "/pending", label: "Pending", icon: ClockIcon },
  { href: "/analytics", label: "Analytics", icon: BarChartIcon },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <Link href="/" className="sidebar-brand">
        <span className="sidebar-brand-mark" aria-hidden="true">
          A
        </span>
        <span className="sidebar-brand-name">AutoApply</span>
      </Link>

      <nav className="sidebar-nav" aria-label="Primary">
        <ul>
          {NAV_LINKS.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={`sidebar-link${isActive ? " sidebar-link-active" : ""}`}
                  aria-current={isActive ? "page" : undefined}
                >
                  <Icon className="sidebar-link-icon" />
                  <span>{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <span className="sidebar-footer-dot" aria-hidden="true" />
        Single-user pipeline
      </div>
    </aside>
  );
}
