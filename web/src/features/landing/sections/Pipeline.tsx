import shared from "../landing.module.css";
import { Backdrop } from "./Backdrop";
import styles from "./Pipeline.module.css";

const STAGES = ["QUEUED", "EXPANDING", "RUNNING", "AGGREGATING", "COMPLETED"];

/** Five stages, pinned: scrolling advances the stage, and the right side follows. */
export function Pipeline() {
  return (
    <section id="pipeline" className={styles.pipeline} data-pin="" data-stages={STAGES.length}>
      <div className={styles.stage}>
        <Backdrop src="/bg/dots.svg" size="22px" fade="edges" opacity={0.8} parallax={-60} />
        <div className={styles.left}>
          <div className={shared.eyebrow}>how a submission runs</div>
          <h2 className={shared.h2}>Five stages. One log.</h2>
          <ol className={styles.crumbs}>
            <span className={styles.rail} aria-hidden="true" />
            <span className={styles.railFill} aria-hidden="true" />
            {STAGES.map((s, i) => (
              <li key={s} data-crumb={i} className={styles.crumb}>
                {String(i + 1).padStart(2, "0")} {s}
              </li>
            ))}
          </ol>
        </div>

        <div className={styles.right}>
          <div data-step="0" className={styles.step}>
            <p className={styles.say}>
              Submit a system prompt. Pick any model on the problem&apos;s allow-list, and run the
              samples first if you like.
            </p>
            <pre className={styles.pre}>
              {"$ curl -X POST /v1/submissions \\\n    -d '{\"problem_id\": \"…\", \"mode\": \"submit\", \"prompt\": \"…\"}'\n"}
              <span className={styles.dim}>{"→ 202 accepted  submission 48213\n→ queued        position 3"}</span>
            </pre>
          </div>

          <div data-step="1" className={styles.step}>
            <p className={styles.say}>
              The problem fans out into sample and hidden tests. Every test runs under the same
              limits.
            </p>
            <div className={styles.limits}>
              {[
                ["TIME", "120 s"],
                ["TOKENS", "60,000"],
                ["STEPS", "40"],
                ["TESTS", "3 + 17 hidden"],
                ["MODELS", "allow-list"],
                ["TEMP", "0.0"],
              ].map(([k, v]) => (
                <div key={k} className={styles.limit}>
                  <div className={styles.k}>{k}</div>
                  <div className={styles.v}>{v}</div>
                </div>
              ))}
            </div>
          </div>

          <div data-step="2" className={styles.step}>
            <p className={styles.say}>
              Every model call goes through the Orqen proxy, which meters it. Sample traces are
              yours to read. Hidden traces stay hidden.
            </p>
            <div className={styles.box}>
              <div className={styles.call}>
                <span className={styles.faint}>01</span>
                <span>read_file(&quot;src/lexer.rs&quot;)</span>
                <span className={styles.dim}>312 lines</span>
              </div>
              <div className={styles.call}>
                <span className={styles.faint}>02</span>
                <span>run(&quot;cargo test lexer&quot;)</span>
                <span className={styles.fail}>exit 101</span>
              </div>
              <div className={styles.call}>
                <span className={styles.faint}>03</span>
                <span>write_file(&quot;src/lexer.rs&quot;, +2 −1)</span>
                <span className={styles.dim}>ok</span>
              </div>
              <div className={styles.rule} />
              {[62, 38, 80].map((w, i) => (
                <div key={w} className={styles.redacted}>
                  <span className={styles.faint}>0{i + 1}</span>
                  <span className={styles.bar} style={{ width: `${w}%` }} />
                </div>
              ))}
              <div className={styles.faint}>hidden test · 14 tool calls · trace redacted</div>
            </div>
          </div>

          <div data-step="3" className={styles.step}>
            <p className={styles.say}>
              Infrastructure faults are retried up to three times and never count against you.
            </p>
            <div className={styles.box}>
              {[1, 2].map((n) => (
                <div key={n} className={styles.retry}>
                  <span>#13</span>
                  <span className={styles.sys}>SYSTEM_ERROR</span>
                  <span>
                    <span className={styles.tag}>retry {n}/3</span>
                  </span>
                </div>
              ))}
              <div className={styles.retry}>
                <span>#13</span>
                <span className={styles.pass}>PASS</span>
                <span className={styles.dim}>attempt 3/3</span>
              </div>
            </div>
          </div>

          <div data-step="4" className={styles.step}>
            <p className={styles.say}>
              A score from 0 to 100, a token count and a verdict per test. Your best score per
              problem goes on the leaderboard.
            </p>
            <div className={styles.result}>
              <div className={styles.score}>70 / 100</div>
              <div className={styles.verdicts}>
                <span className={styles.pass}>14 PASS</span>
                <span className={styles.fail}>2 FAIL</span>
                <span className={styles.limit}>1 TLE</span>
                <span className={styles.limitC}>1 MLE</span>
                <span className={styles.err}>1 ERROR</span>
                <span className={styles.budget}>1 BUDGET</span>
              </div>
              <div className={styles.dim}>213,844 tokens · 4m 12s wall</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
