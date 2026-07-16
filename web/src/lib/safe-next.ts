// Only same-origin paths. "//host" and "/\host" are protocol-relative to browsers, and
// tabs or newlines are stripped before parsing, so "/\t/host" would become "//host".
const SAME_ORIGIN_PATH = /^\/(?![/\\])[^\\\u0000-\u001f]*$/

export function safeNext(next: string | null | undefined, fallback = "/"): string {
  return next && SAME_ORIGIN_PATH.test(next) ? next : fallback
}
