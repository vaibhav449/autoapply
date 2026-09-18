/** 1-2 letter avatar initials from a full name. Was defined identically in
 * match-list.tsx, profiles/page.tsx, and profiles/[id]/page.tsx. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
