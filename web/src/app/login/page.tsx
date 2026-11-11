import type { Metadata } from "next";
import Link from "next/link";

import { Notice } from "@/components";
import { PASSWORD_MAX, PASSWORD_MIN } from "@/lib/password";
import { safeNext } from "@/lib/safe-next";

import styles from "./page.module.css";

export const metadata: Metadata = { title: "sign in" };

const ERRORS: Record<string, string> = {
  provider: "that sign-in provider isn't enabled",
  start: "couldn't start sign-in; try again",
  callback: "sign-in was cancelled",
  exchange: "the sign-in link expired or was already used; try again",
  link: "that email link expired or was already used; ask for a new one",
  account: "signed in, but your Orqen account couldn't be created; try again shortly",
  session: "your session ended; sign in again",
  credentials: "wrong email or password",
  unconfirmed: "confirm your email first; check your inbox for the link",
  email: "enter a valid email address",
  weak: `use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters, not a common password`,
  mismatch: "the two passwords don't match",
  signup: "couldn't create the account; try again",
  rate: "too many attempts; wait a minute and try again",
};

const NOTICES: Record<string, string> = {
  confirm: "check your inbox: confirm your email, then sign in",
  reset: "if that email has an account, a reset link is on its way",
};

type Mode = "signin" | "signup" | "forgot";
const TITLES: Record<Mode, string> = {
  signin: "Sign in to submit agents",
  signup: "Create your Orqen account",
  forgot: "Reset your password",
};

type Props = {
  searchParams: Promise<{ error?: string; notice?: string; next?: string; mode?: string }>;
};

export default async function LoginPage({ searchParams }: Props) {
  const q = await searchParams;
  const next = safeNext(q.next);
  const mode: Mode = q.mode === "signup" || q.mode === "forgot" ? q.mode : "signin";
  const modeHref = (m: Mode) => `/login?mode=${m}&next=${encodeURIComponent(next)}`;
  const github = `/auth/login?provider=github&next=${encodeURIComponent(next)}`;

  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <div className={styles.head}>
          <span className={styles.block} aria-hidden="true" />
          <span>orqen</span>
          <span className={styles.tag}>judge for agents</span>
        </div>
        <div className={styles.body}>
          <h1 className={styles.title}>{TITLES[mode]}</h1>
          {mode === "signin" && (
            <div className={styles.lines} aria-hidden="true">
              <span style={{ animationDelay: "60ms" }}>
                <span className={styles.ok}>✓</span> prompts and agents judged on hidden tests
              </span>
              <span style={{ animationDelay: "140ms" }}>
                <span className={styles.ok}>✓</span> token budgets, step caps, live verdicts
              </span>
              <span style={{ animationDelay: "220ms" }}>
                <span className={styles.ok}>✓</span> free trial: $1 of model credit for 7 days
              </span>
            </div>
          )}
          {q.error && (
            <Notice tone="error" tag="auth">
              {ERRORS[q.error] ?? "sign-in failed"}
            </Notice>
          )}
          {q.notice && NOTICES[q.notice] && (
            <Notice tone="info" tag="mail">
              {NOTICES[q.notice]}
            </Notice>
          )}

          {mode !== "forgot" && (
            <>
              <a className={styles.oauth} href={github}>
                <span aria-hidden="true">⌥</span> Continue with GitHub
              </a>
              <div className={styles.or} aria-hidden="true">
                <span>or with email</span>
              </div>
            </>
          )}

          <form className={styles.form} method="post" action="/auth/password">
            <input type="hidden" name="intent" value={mode} />
            <input type="hidden" name="next" value={next} />
            <label className={styles.field}>
              <span>email</span>
              <input
                name="email"
                type="email"
                autoComplete="email"
                required
                maxLength={254}
                autoFocus
              />
            </label>
            {mode !== "forgot" && (
              <label className={styles.field}>
                <span>
                  password
                  {mode === "signin" && (
                    <Link className={styles.aside} href={modeHref("forgot")}>
                      forgot?
                    </Link>
                  )}
                </span>
                <input
                  name="password"
                  type="password"
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  required
                  minLength={mode === "signup" ? PASSWORD_MIN : undefined}
                  maxLength={PASSWORD_MAX}
                />
              </label>
            )}
            {mode === "signup" && (
              <label className={styles.field}>
                <span>confirm password</span>
                <input
                  name="confirm"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={PASSWORD_MIN}
                  maxLength={PASSWORD_MAX}
                />
              </label>
            )}
            <button className={styles.submit} type="submit">
              {mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"}
            </button>
          </form>

          <p className={styles.switch}>
            {mode === "signin" ? (
              <>
                New here? <Link href={modeHref("signup")}>Create an account</Link>
              </>
            ) : (
              <>
                Have an account? <Link href={modeHref("signin")}>Sign in</Link>
              </>
            )}
          </p>
          <p className={styles.fine}>
            Orqen keeps your session in an httpOnly cookie. Supabase stores your password
            hashed; Orqen never sees it. Leaderboards show your handle, never your email.
          </p>
        </div>
        <div className={styles.foot}>
          <span className={styles.mode}>-- {mode === "signup" ? "SIGN UP" : mode === "forgot" ? "RESET" : "SIGN IN"} --</span>
          <span>{mode === "forgot" ? "email link" : "oauth · pkce · password"}</span>
        </div>
      </div>
    </main>
  );
}
