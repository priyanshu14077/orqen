/** A same-site path to return to after sign-in. Anything else becomes "/". */
export function safeNext(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/";
  }
  return value.slice(0, 512);
}
