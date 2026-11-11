/** A same-site path to return to after sign-in. Anything else becomes "/problems". */
export function safeNext(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/problems";
  }
  return value.slice(0, 512);
}
