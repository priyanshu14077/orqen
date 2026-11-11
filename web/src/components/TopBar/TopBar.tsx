"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Handle } from "../Handle/Handle";
import styles from "./TopBar.module.css";

/** `match` is a RegExp source string: props from server components must be serializable. */
export type Tab = { key: string; label: string; href: string; match: string };

type Props = { tabs: Tab[]; handle: string; plan: string | null };

/**
 * Brand, numbered screen tabs, and the signed-in handle. Keys 1–9 switch tabs, except
 * while typing in an input, textarea or select (docs/frontend §2).
 */
export function TopBar({ tabs, handle, plan }: Props) {
  const path = usePathname();
  const router = useRouter();
  const tabsRef = useRef<HTMLElement>(null);
  const [bar, setBar] = useState({ left: 0, width: 0, visible: false });
  const active = tabs.findIndex((t) => new RegExp(t.match).test(path));

  useLayoutEffect(() => {
    const el = tabsRef.current?.querySelectorAll<HTMLElement>("a")[active];
    setBar(el ? { left: el.offsetLeft, width: el.offsetWidth, visible: true } : (b) => ({ ...b, visible: false }));
  }, [active, path]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || t.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tab = tabs[Number(e.key) - 1];
      if (tab) router.push(tab.href);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tabs, router]);

  return (
    <header className={styles.bar}>
      <Link href="/" className={styles.brand} aria-label="orqen home">
        <span className={styles.block} aria-hidden="true" />
        <span>orqen</span>
        <span className={styles.tagline}>judge for agents</span>
      </Link>
      <nav ref={tabsRef} className={styles.tabs} aria-label="screens">
        {tabs.map((t, i) => (
          <Link key={t.key} href={t.href} className={styles.tab} aria-current={i === active ? "page" : undefined}>
            <span className={styles.n} aria-hidden="true">
              {i + 1}
            </span>
            <span>{t.label}</span>
          </Link>
        ))}
        <span
          className={styles.indicator}
          style={{ left: bar.left, width: bar.width, opacity: bar.visible ? 1 : 0 }}
          aria-hidden="true"
        />
      </nav>
      <span className={styles.fill} />
      <div className={styles.right}>
        {plan && <span className={styles.plan}>{plan.replace("_", " ")}</span>}
        <Handle handle={handle} />
        <form action="/auth/logout" method="post">
          <button type="submit" className={styles.signout}>
            sign out
          </button>
        </form>
      </div>
    </header>
  );
}
