import Link from "next/link";
import type { ReactElement } from "react";

export default function SiteFooter(): ReactElement {
  const year = new Date().getFullYear();

  return (
    <footer className="colophon">
      <div className="wrap colophon-inner">
        <div>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <a href="mailto:support@yourdomain.com">Contact</a>
        </div>
        <div>Debate Coach, {year}</div>
      </div>
    </footer>
  );
}
