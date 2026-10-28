import { Season } from "./types";

/** Short month names, January first. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-09" to "Sep 2026". */
export function monthLabel(month: string): string {
  const [year, number] = month.split("-");
  return `${MONTHS[Number(number) - 1]} ${year}`;
}

/** A season's months as "Sep 2026 – Jan 2027", or one month alone. */
export function seasonSpan(season: Pick<Season, "starts" | "ends">): string {
  return season.starts === season.ends
    ? monthLabel(season.starts)
    : `${monthLabel(season.starts)} – ${monthLabel(season.ends)}`;
}

/** Season the page opens on: the one holding today, else the latest; null for all time. */
export function defaultSeason(seasons: Season[], today: string): Season | null {
  const month = today.slice(0, 7);
  const current = seasons
    .filter((season) => season.starts <= month && month <= season.ends)
    .sort((a, b) => b.starts.localeCompare(a.starts));
  if (current.length > 0) return current[0];
  const past = [...seasons].sort((a, b) => b.ends.localeCompare(a.ends) || b.starts.localeCompare(a.starts));
  return past[0] ?? null;
}
