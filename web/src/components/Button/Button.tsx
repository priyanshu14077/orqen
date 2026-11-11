import type { ButtonHTMLAttributes } from "react";

import styles from "./Button.module.css";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "ghost" | "outline" | "primary" | "success";
  size?: "sm" | "md" | "lg";
};

/** Square, 1px-bordered buttons. `primary` is the one filled action per screen. */
export function Button({ variant = "ghost", size = "sm", className = "", ...rest }: Props) {
  const cls = [styles.button, size !== "sm" && styles[size], variant !== "ghost" && styles[variant]]
    .filter(Boolean)
    .join(" ");
  return <button type="button" className={`${cls} ${className}`} {...rest} />;
}
