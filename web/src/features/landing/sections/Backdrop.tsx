import styles from "./Backdrop.module.css";

type Props = {
  /** Any image under web/public, such as "/bg/grid.svg". Add files there to get more. */
  src: string;
  /** CSS background-size: a tile size like "48px", or "cover". */
  size?: string;
  opacity?: number;
  /** Where the pattern fades out. */
  fade?: "radial" | "top" | "bottom" | "edges" | "none";
  /** Slowly pans the pattern. Off under prefers-reduced-motion. */
  drift?: boolean;
  /** Moves with the parent pin's --p, for depth. Pixels of travel over the pin. */
  parallax?: number;
};

/** A decorative background layer: fills its positioned parent, never takes clicks. */
export function Backdrop({ src, size = "48px", opacity = 1, fade = "radial", drift, parallax }: Props) {
  return (
    <div
      aria-hidden="true"
      className={`${styles.backdrop} ${styles[fade]} ${drift ? styles.drift : ""}`}
      style={
        {
          backgroundImage: `url("${src}")`,
          backgroundSize: size,
          opacity,
          "--travel": parallax ? `${parallax}px` : undefined,
        } as React.CSSProperties
      }
    />
  );
}
