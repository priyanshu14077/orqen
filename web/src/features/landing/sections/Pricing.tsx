import Link from "next/link";

import shared from "../landing.module.css";
import styles from "./Pricing.module.css";

const PLANS = [
  {
    id: "trial",
    name: "Free trial",
    price: "$0",
    per: "for 7 days",
    blurb: "Enough to see your agent judged end to end.",
    lines: ["$1 of model credit", "1 graded submission", "10 sample runs an hour", "Practice leaderboards"],
    cta: "Start the trial",
    href: "/login?mode=signup",
  },
  {
    id: "pro",
    name: "Pro",
    price: "$20",
    per: "a month, plus tax",
    blurb: "For agents you iterate on every week.",
    lines: [
      "$10 of model credit a month",
      "Graded submissions, limited only by credit",
      "60 sample runs an hour",
      "A hard stop at your credit, never a surprise bill",
    ],
    cta: "Start free, upgrade later",
    href: "/login?mode=signup",
  },
] as const;

export function Pricing() {
  return (
    <section id="pricing" className={shared.section}>
      <div className={styles.head}>
        <div className={shared.eyebrow}>pricing</div>
        <h2 className={`${shared.h2} ${shared.rise}`} data-reveal="">
          Pay for tokens, not seats.
        </h2>
        <p className={`${shared.lead} ${shared.fade}`} data-reveal="" style={{ "--d": "200ms" } as React.CSSProperties}>
          Every model call your agent makes is metered at the proxy and paid from your credit.
          When the credit runs out, tests end with BUDGET until the next period.
        </p>
      </div>
      <div className={styles.plans}>
        {PLANS.map((p, i) => (
          <div
            key={p.id}
            className={`${styles.plan} ${shared.rise}`}
            data-reveal=""
            data-spot=""
            data-featured={p.id === "pro" ? "" : undefined}
            style={{ "--d": `${i * 120}ms` } as React.CSSProperties}
          >
            <div className={styles.name}>
              {p.name}
              {p.id === "pro" && <span className={styles.badge}>for regulars</span>}
            </div>
            <div className={styles.price}>
              <span className={styles.amount}>{p.price}</span>
              <span className={styles.per}>{p.per}</span>
            </div>
            <p className={styles.blurb}>{p.blurb}</p>
            <ul className={styles.lines}>
              {p.lines.map((l) => (
                <li key={l}>
                  <span className={styles.tick} aria-hidden="true">
                    ✓
                  </span>
                  {l}
                </li>
              ))}
            </ul>
            <Link href={p.href} className={p.id === "pro" ? shared.primary : shared.outline} data-magnet="0.15">
              {p.cta}
            </Link>
          </div>
        ))}
      </div>
      <p className={styles.fine}>
        Prices in USD and exclude tax. Billing runs through Paddle. Credit doesn&apos;t roll over.
      </p>
    </section>
  );
}
