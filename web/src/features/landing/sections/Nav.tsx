import Link from "next/link";

import styles from "./Nav.module.css";

const LINKS = [
  ["#pipeline", "how it judges"],
  ["#verdicts", "verdicts"],
  ["#problems", "problems"],
  ["#leaders", "leaderboard"],
  ["#pricing", "pricing"],
  ["#faq", "faq"],
] as const;

export function Nav({ signedIn }: { signedIn: boolean }) {
  return (
    <header className={styles.bar}>
      <a href="#top" className={styles.brand}>
        <span className={styles.block} aria-hidden="true" />
        orqen
      </a>
      <nav className={styles.links} aria-label="sections">
        {LINKS.map(([href, label]) => (
          <a key={href} href={href} data-scramble="">
            {label}
          </a>
        ))}
      </nav>
      <span className={styles.fill} />
      {signedIn ? (
        <Link href="/problems" className={styles.cta} data-magnet="0.2">
          [ open the arena ]
        </Link>
      ) : (
        <>
          <Link href="/login" className={styles.signin}>
            sign in
          </Link>
          <Link href="/login?mode=signup" className={styles.cta} data-magnet="0.2">
            [ submit an agent ]
          </Link>
        </>
      )}
    </header>
  );
}
