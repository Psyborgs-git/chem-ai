/** Agent citations may navigate only to the public handbook inside this app. */
export function isStudioHelpLink(href: string): boolean {
  return /^\/help(?:\/(?:usage|development|operations|reference)\/[a-z0-9]+(?:-[a-z0-9]+)*)?(?:#[\p{L}\p{N}_%~-]+)?$/u.test(href);
}
