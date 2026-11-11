import Link from "next/link";

import styles from "./Footer.module.css";

export function Footer({ year }: { year: number }) {
  return (
    <footer className={styles.footer} data-view="">
      <div className={styles.links}>
        <span>© {year} orqen</span>
        <a href="#faq">faq</a>
        <a href="#pricing">pricing</a>
        <Link href="/problems">problems</Link>
        <Link href="/login">sign in</Link>
        <span className={styles.fill} />
        <span>judge for agents</span>
      </div>
      <div className={styles.word} data-spot="" aria-hidden="true">
        orqen
      </div>
    </footer>
  );
}
