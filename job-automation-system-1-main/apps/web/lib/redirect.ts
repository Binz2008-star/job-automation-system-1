export function resolveNextPath(
  next: string | null | undefined,
  fallback: string
): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) {
    return fallback;
  }
  return next;
}

export function buildAuthHref(
  basePath: "/login" | "/signup",
  next?: string | null
): string {
  const safeNext = resolveNextPath(next, "");
  if (!safeNext) return basePath;
  return `${basePath}?next=${encodeURIComponent(safeNext)}`;
}
