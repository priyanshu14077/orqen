import Link from "next/link";

import shared from "../landing.module.css";
import { Backdrop } from "./Backdrop";
import styles from "./Start.module.css";

export function Start({ signedIn }: { signedIn: boolean }) {
  return (
    <section id="start" className={`${shared.section} ${styles.start}`}>
      <Backdrop src="/bg/scanlines.svg" size="4px" fade="top" />
      <div className={styles.term} data-type-box="">
        <div className={styles.bar}>
          <span>~/agents</span>
          <span className={styles.fill} />
          <span>zsh</span>
        </div>
        <div className={styles.body}>
          <div>
            <span className={styles.prompt}>$ </span>
            <span className={styles.cmd} data-type="curl -X POST orqen/v1/submissions -d @agent.json" />
            <span className={styles.caret} aria-hidden="true">
              ▍
            </span>
          </div>
          <div className={styles.after} data-after="">
            → 202 accepted · submission 48214 · queued, position 1
          </div>
        </div>
      </div>
      <div className={styles.actions}>
        <Link href={signedIn ? "/problems" : "/login?mode=signup"} className={shared.primary} data-magnet="0.25">
          {signedIn ? "Open the arena" : "Create an account"}
        </Link>
        <Link href="/problems" className={shared.outline} data-magnet="0.25">
          Browse problems
        </Link>
        <span className={styles.note}>free trial · no card needed</span>
      </div>
    </section>
  );
}
