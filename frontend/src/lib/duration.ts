/**
 * Formats a whole number of seconds as a short human-readable duration,
 * e.g. 1028 -> "17m 8s", 3723 -> "1h 2m 3s", 45 -> "45s".
 *
 * Pure formatting only — the seconds value itself must come from the
 * backend (real PrusaSlicer output). No manufacturing calculation happens
 * here or anywhere else in the frontend.
 */
export function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) {
    return "—";
  }

  const seconds = Math.round(totalSeconds);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0 || hours > 0) parts.push(`${minutes}m`);
  parts.push(`${secs}s`);

  return parts.join(" ");
}

/** Formats a gram quantity from the backend, e.g. 3.95 -> "3.95g". */
export function formatGrams(grams: number): string {
  if (!Number.isFinite(grams)) return "—";
  return `${grams.toFixed(2)}g`;
}

/** A shorter duration for compact UI (constraint-limit footers, chips) —
 * same real value as formatDuration, just without a redundant ":00"
 * seconds component when the limit is a round number, e.g. 2700 -> "45m"
 * instead of "45m 0s". */
export function formatDurationCompact(totalSeconds: number): string {
  const full = formatDuration(totalSeconds);
  return full.replace(/ 0s$/, "");
}
