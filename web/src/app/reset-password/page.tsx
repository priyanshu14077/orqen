import type { Metadata } from "next";

import { Notice } from "@/components";
import { PASSWORD_MAX, PASSWORD_MIN } from "@/lib/password";

import styles from "../login/page.module.css";

export const metadata: Metadata = { title: "new password" };

const ERRORS: Record<string, string> = {
  weak: `use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters, not a common password`,
  mismatch: "the two passwords don't match",
  same: "pick a password different from the old one",
  update: "couldn't update the password; open the reset link again",
};

type Props = { searchParams: Promise<{ error?: string }> };

/** Reached from the reset email (via /auth/confirm), which signs the user in first. */
export default async function ResetPasswordPage({ searchParams }: Props) {
  const { error } = await searchParams;
  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <div className={styles.head}>
          <span className={styles.block} aria-hidden="true" />
          <span>orqen</span>
          <span className={styles.tag}>judge for agents</span>
        </div>
        <div className={styles.body}>
          <h1 className={styles.title}>Choose a new password</h1>
          {error && (
            <Notice tone="error" tag="auth">
              {ERRORS[error] ?? "couldn't update the password"}
            </Notice>
          )}
          <form className={styles.form} method="post" action="/auth/password">
            <input type="hidden" name="intent" value="update" />
            <label className={styles.field}>
              <span>new password</span>
              <input
                name="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={PASSWORD_MIN}
                maxLength={PASSWORD_MAX}
                autoFocus
              />
            </label>
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
            <button className={styles.submit} type="submit">
              Save password
            </button>
          </form>
        </div>
        <div className={styles.foot}>
          <span className={styles.mode}>-- RESET --</span>
          <span>signed in by email link</span>
        </div>
      </div>
    </main>
  );
}
