/**
 * Scroll and pointer effects for the landing page, wired by data attributes so the
 * sections stay server components. Effects write CSS custom properties and data
 * attributes; the CSS modules decide what those look like.
 *
 *   data-pin             --p: 0→1 while the element scrolls past its sticky child
 *   data-stages="n"      also marks the current stage on [data-step] and [data-crumb]
 *   data-skew            --vel: scroll velocity, -1→1, easing back to 0
 *   data-view            --v: how much of the element has entered the viewport, 0→1
 *   data-reveal          data-in once the element scrolls into view
 *   data-spot            --mx, --my: pointer position inside the element
 *   data-magnet="0.25"   leans towards the pointer
 *   data-scramble        scrambles its text on hover, then settles
 *   data-type="text"     types the text once visible, then marks [data-after] in its box
 *
 * With `reduced` set (prefers-reduced-motion), only effects the reader drives by
 * scrolling remain: pins and stages. Everything else shows its final state at once.
 */

const GLYPHS = "!<>-_\\/[]{}=+*^?#01";

/** Every attribute this module wires up. */
export const MOTION_SELECTOR = [
  "[data-pin]",
  "[data-view]",
  "[data-skew]",
  "[data-reveal]",
  "[data-spot]",
  "[data-magnet]",
  "[data-scramble]",
  "[data-type]",
].join(",");

const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));

export function mountMotion(root: HTMLElement, reduced: boolean): () => void {
  const off: (() => void)[] = [];
  const on = <K extends keyof WindowEventMap>(
    target: Window | HTMLElement,
    type: K | string,
    fn: (e: Event) => void,
  ) => {
    target.addEventListener(type, fn, { passive: true });
    off.push(() => target.removeEventListener(type, fn));
  };
  const all = (sel: string) => Array.from(root.querySelectorAll<HTMLElement>(sel));

  // Scroll-linked: pins, stages, view and velocity, batched into one frame.
  const pins = all("[data-pin]");
  const views = all("[data-view]");
  const skews = all("[data-skew]");
  let frame = 0;
  let lastY = window.scrollY;
  let lastT = performance.now();
  let vel = 0;

  const paint = () => {
    frame = 0;
    const vh = window.innerHeight;
    for (const el of pins) {
      const rect = el.getBoundingClientRect();
      const run = el.offsetHeight - vh;
      const p = run > 0 ? clamp(-rect.top / run) : rect.top < 0 ? 1 : 0;
      el.style.setProperty("--p", p.toFixed(4));
      const n = Number(el.dataset.stages);
      if (n > 0) {
        const stage = String(Math.min(n - 1, Math.floor(p * n)));
        if (el.dataset.stage !== stage) {
          el.dataset.stage = stage;
          for (const s of el.querySelectorAll<HTMLElement>("[data-step]")) {
            s.toggleAttribute("data-on", s.dataset.step === stage);
          }
          for (const c of el.querySelectorAll<HTMLElement>("[data-crumb]")) {
            c.toggleAttribute("data-on", Number(c.dataset.crumb) <= Number(stage));
          }
        }
      }
    }
    for (const el of views) {
      const rect = el.getBoundingClientRect();
      el.style.setProperty("--v", clamp((vh - rect.top) / Math.max(1, rect.height)).toFixed(4));
    }
    if (!reduced && skews.length) {
      const now = performance.now();
      const dy = window.scrollY - lastY;
      const dt = Math.max(1, now - lastT);
      lastY = window.scrollY;
      lastT = now;
      vel = vel * 0.86 + clamp(dy / dt / 4, -1, 1) * 0.14;
      if (Math.abs(vel) < 0.002) vel = 0;
      for (const el of skews) el.style.setProperty("--vel", vel.toFixed(4));
      if (vel !== 0) frame = requestAnimationFrame(paint);
    }
  };
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(paint);
  };
  on(window, "scroll", schedule);
  on(window, "resize", schedule);
  paint();
  off.push(() => cancelAnimationFrame(frame));

  // Reveal on first sight.
  const reveals = all("[data-reveal]");
  if (reduced || !("IntersectionObserver" in window)) {
    for (const el of reveals) el.setAttribute("data-in", "");
  } else {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          e.target.setAttribute("data-in", "");
          io.unobserve(e.target);
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    for (const el of reveals) io.observe(el);
    off.push(() => io.disconnect());
  }

  // Typewriter.
  // data-typed: already typed, so a re-mount after streaming doesn't type it again.
  const typers = all("[data-type]:not([data-typed])");
  const timers: number[] = [];
  off.push(() => timers.forEach((t) => clearTimeout(t)));
  const done = (el: HTMLElement) => {
    el.setAttribute("data-typed", "");
    el.textContent = el.dataset.type ?? "";
    el.closest("[data-type-box]")?.querySelector("[data-after]")?.setAttribute("data-in", "");
  };
  if (reduced || !("IntersectionObserver" in window)) {
    typers.forEach(done);
  } else {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          io.unobserve(e.target);
          const el = e.target as HTMLElement;
          const text = el.dataset.type ?? "";
          let i = 0;
          const tick = () => {
            el.textContent = text.slice(0, ++i);
            if (i < text.length) timers.push(window.setTimeout(tick, 28 + Math.random() * 40));
            else timers.push(window.setTimeout(() => done(el), 380));
          };
          timers.push(window.setTimeout(tick, 300));
        }
      },
      { threshold: 0.6 },
    );
    for (const el of typers) io.observe(el);
    off.push(() => io.disconnect());
  }

  if (reduced) return () => off.forEach((f) => f());

  // Pointer effects. Touch screens get none of them.
  const fine = window.matchMedia("(pointer: fine)").matches;
  if (fine) {
    for (const el of all("[data-spot]")) {
      on(el, "pointermove", (e) => {
        const ev = e as PointerEvent;
        const r = el.getBoundingClientRect();
        el.style.setProperty("--mx", `${ev.clientX - r.left}px`);
        el.style.setProperty("--my", `${ev.clientY - r.top}px`);
      });
    }
    for (const el of all("[data-magnet]")) {
      const pull = Number(el.dataset.magnet) || 0.25;
      on(el, "pointermove", (e) => {
        const ev = e as PointerEvent;
        const r = el.getBoundingClientRect();
        const x = (ev.clientX - r.left - r.width / 2) * pull;
        const y = (ev.clientY - r.top - r.height / 2) * pull;
        el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
      });
      on(el, "pointerleave", () => {
        el.style.transform = "";
      });
    }
    for (const el of all("[data-scramble]")) {
      const text = el.textContent ?? "";
      let run = 0;
      on(el, "pointerenter", () => {
        const id = ++run;
        let step = 0;
        const tick = () => {
          if (id !== run) return;
          step += 1;
          const settled = Math.floor((step / 14) * text.length);
          el.textContent = [...text]
            .map((ch, i) =>
              i < settled || ch === " " ? ch : GLYPHS[Math.floor(Math.random() * GLYPHS.length)],
            )
            .join("");
          if (settled < text.length) requestAnimationFrame(tick);
          else el.textContent = text;
        };
        tick();
      });
      off.push(() => {
        run += 1;
        el.textContent = text;
      });
    }
  }

  return () => off.forEach((f) => f());
}
