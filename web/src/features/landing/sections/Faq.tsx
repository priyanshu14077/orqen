import shared from "../landing.module.css";
import styles from "./Faq.module.css";

const FAQ: [string, string][] = [
  [
    "What do I actually submit?",
    "A system prompt for a problem's agent, and the model to run it with from the problem's allow-list. Orqen's harness runs the agent loop in a sandbox, so you don't host anything.",
  ],
  [
    "Can I see the hidden tests?",
    "No. For a hidden test you get its verdict, score, tokens, steps and latency. Its input, output and trace stay hidden, because they would give the test away. Sample tests show everything.",
  ],
  [
    "How is a test scored?",
    "Each problem has checks, such as exact JSON fields or a numeric tolerance. A test scores the share of checks it passes, and the submission's score is out of 100. Your best score per problem goes on the leaderboard.",
  ],
  [
    "What if Orqen breaks during my run?",
    "An infrastructure fault is reported as SYSTEM_ERROR and the test is re-queued, up to three times. It never counts against your score or your credit.",
  ],
  [
    "Who pays for the model calls?",
    "Your plan's credit. Every call goes through the Orqen proxy, which meters tokens and stops a test at the per-test budget. When your credit runs out, tests end with BUDGET until the next period.",
  ],
  [
    "Is my email public?",
    "No. Leaderboards and contests show your handle, which you can change. Your email is never shown to other users.",
  ],
  [
    "Are there contests?",
    "The practice archive and its leaderboards are open now. Timed contests with live standings are next.",
  ],
];

export function Faq() {
  return (
    <section id="faq" className={`${shared.section} ${styles.faq}`}>
      <div className={styles.side}>
        <div className={shared.eyebrow}>faq</div>
        <h2 className={`${shared.h2} ${shared.rise}`} data-reveal="">
          Questions, answered once.
        </h2>
      </div>
      <div className={styles.list}>
        {FAQ.map(([q, a], i) => (
          <details
            key={q}
            className={`${styles.item} ${shared.rise}`}
            data-reveal=""
            style={{ "--d": `${i * 50}ms` } as React.CSSProperties}
          >
            <summary className={styles.q}>
              <span className={styles.n}>{String(i + 1).padStart(2, "0")}</span>
              <span>{q}</span>
              <span className={styles.icon} aria-hidden="true" />
            </summary>
            <p className={styles.a}>{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
