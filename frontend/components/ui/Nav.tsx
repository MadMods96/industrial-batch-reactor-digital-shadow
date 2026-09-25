"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "Floor"],
  ["/batches", "Batches"],
  ["/simulate", "What-if"],
  ["/data", "Data"],
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="app-nav">
      <div className="brand">
        <strong>HTPP</strong>
        <span>Digital Shadow</span>
      </div>
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href} className={path === href ? "active" : ""}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
